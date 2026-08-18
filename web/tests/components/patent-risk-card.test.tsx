import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import type { PatentAnalysis } from "@praviar/shared-types";
import { PatentRiskCard } from "@/components/patent/patent-risk-card";
import {
  getPatentJurisdictionCode,
  getRiskBorderClass,
} from "@/components/patent/patent-risk-card-helpers";

const feedbackModalSpy = vi.fn();

vi.mock("@/components/collaboration/feedback-modal", () => ({
  FeedbackModal: (props: any) => {
    feedbackModalSpy(props);
    return props.open ? (
      <div data-testid="feedback-modal">feedback modal</div>
    ) : null;
  },
}));

function makeAnalysis(overrides: Partial<PatentAnalysis> = {}): PatentAnalysis {
  return {
    patent_id: "US1234567B2",
    title: "Fermentation process",
    assignee: "Fictional Meridian Therapeutics",
    expiry_date: "2038-01-15",
    claims_analyzed: [
      {
        claim_number: 1,
        claim_type: "independent",
        depends_on: null,
        preamble: "",
        transitional_phrase: "",
        elements: [],
        overall_status: "met",
        overall_confidence: 0.9,
        reasoning: "",
      },
      {
        claim_number: 2,
        claim_type: "dependent",
        depends_on: 1,
        preamble: "",
        transitional_phrase: "",
        elements: [],
        overall_status: "not_met",
        overall_confidence: 0.3,
        reasoning: "",
      },
    ],
    risk_level: "high",
    risk_summary: "High risk because of broad fermentation claims.",
    design_around_suggestions: [
      {
        element_avoided: 2,
        suggestion: "Use a non-bacterial host.",
        feasibility: "medium",
      },
    ],
    orange_book_info: {
      is_listed: true,
      product_names: ["Drug A"],
      active_ingredients: ["Ingredient A"],
    },
    model_used: "claude-3-opus",
    thinking_text: "",
    input_tokens: 5000,
    output_tokens: 300,
    ...overrides,
  };
}

describe("patent risk card helpers", () => {
  it("maps known jurisdictions to deterministic codes", () => {
    expect(getPatentJurisdictionCode("US1234567B2")).toBe("US");
    expect(getPatentJurisdictionCode("EP1234567A1")).toBe("EP");
  });

  it("falls back to no code for unknown jurisdictions", () => {
    expect(getPatentJurisdictionCode("ZZ1234567B2")).toBe("");
  });

  it("maps risk levels to border classes", () => {
    expect(getRiskBorderClass("high")).toBe("border-error/20");
    expect(getRiskBorderClass("medium")).toBe("border-warning/20");
    expect(getRiskBorderClass("low")).toBe("border-[var(--border-default)]");
  });
});

describe("PatentRiskCard", () => {
  beforeEach(() => {
    feedbackModalSpy.mockClear();
  });

  it("renders the collapsed summary state", () => {
    render(<PatentRiskCard analysis={makeAnalysis()} />);

    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByLabelText("Jurisdiction US")).toBeInTheDocument();
    expect(screen.getByText("US1234567B2")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Fermentation process — Fictional Meridian Therapeutics",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("2 claims")).toBeInTheDocument();
    expect(screen.getByText("Exp: 2038-01-15")).toBeInTheDocument();
    expect(screen.queryByText("Google Patents")).not.toBeInTheDocument();
  });

  it("expands to show patent links, orange book data, and design-around suggestions", () => {
    render(
      <PatentRiskCard
        analysis={makeAnalysis()}
        analysisId="analysis-123"
        narrative="A focused narrative."
      />,
    );

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText("Google Patents")).toBeInTheDocument();
    expect(screen.getByText("Espacenet")).toBeInTheDocument();
    expect(screen.getByText("A focused narrative.")).toBeInTheDocument();
    expect(screen.getByText("Orange Book Listed")).toBeInTheDocument();
    expect(screen.getByText("Products: Drug A")).toBeInTheDocument();
    expect(
      screen.getByText("Active Ingredients: Ingredient A"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("High risk because of broad fermentation claims."),
    ).toBeInTheDocument();
    expect(screen.getByText("Design-Around Suggestions")).toBeInTheDocument();
    expect(screen.getByText("Element 2:")).toBeInTheDocument();
    expect(screen.getByText("Use a non-bacterial host.")).toBeInTheDocument();
    expect(screen.getByText("Feasibility: medium")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Correct assessment" }),
    ).toBeInTheDocument();
  });

  it("opens the feedback modal when analysisId is present and no callback is provided", () => {
    render(
      <PatentRiskCard analysis={makeAnalysis()} analysisId="analysis-123" />,
    );

    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "Correct assessment" }));

    expect(screen.getByTestId("feedback-modal")).toBeInTheDocument();
    expect(feedbackModalSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({
        analysisId: "analysis-123",
        patentId: "US1234567B2",
        currentRisk: "high",
        open: true,
      }),
    );
  });

  it("renders persisted Orange Book evidence when optional descriptive arrays are absent", () => {
    render(
      <PatentRiskCard
        analysis={makeAnalysis({
          orange_book_info: {
            is_listed: true,
            nda_numbers: ["NDA204671"],
            patent_use_codes: ["U-2608"],
          },
        })}
        defaultExpanded
      />,
    );

    expect(screen.getByText("Orange Book Listed")).toBeInTheDocument();
    expect(screen.getByText("NDA: NDA204671")).toBeInTheDocument();
    expect(screen.getByText("Patent use: U-2608")).toBeInTheDocument();
  });

  it("does not expose attorney feedback controls to non-counsel report viewers", () => {
    render(
      <PatentRiskCard
        analysis={makeAnalysis()}
        analysisId="analysis-123"
        canSubmitFeedback={false}
        defaultExpanded
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Correct assessment" }),
    ).not.toBeInTheDocument();
    expect(feedbackModalSpy).not.toHaveBeenCalled();
  });

  it("prefers the explicit onCorrect callback over the feedback modal", () => {
    const onCorrect = vi.fn();

    render(
      <PatentRiskCard
        analysis={makeAnalysis()}
        analysisId="analysis-123"
        onCorrect={onCorrect}
      />,
    );

    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "Correct assessment" }));

    expect(onCorrect).toHaveBeenCalledTimes(1);
    expect(feedbackModalSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({
        open: false,
      }),
    );
  });

  it("defaults to collapsed state and expands when defaultExpanded is true", () => {
    render(<PatentRiskCard analysis={makeAnalysis()} defaultExpanded />);

    expect(screen.getByText("Google Patents")).toBeInTheDocument();
  });

  it("expands after a mounted card becomes the deep-linked patent", () => {
    const { rerender } = render(
      <PatentRiskCard analysis={makeAnalysis()} defaultExpanded={false} />,
    );

    expect(screen.queryByText("Google Patents")).not.toBeInTheDocument();

    rerender(<PatentRiskCard analysis={makeAnalysis()} defaultExpanded />);

    expect(screen.getByText("Google Patents")).toBeInTheDocument();
  });
});
