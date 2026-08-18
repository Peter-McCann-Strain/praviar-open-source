import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TEST_REPORT } from "../fixtures/report-fixture";
import type {
  FTOReport,
  PatentAnalysis,
  ClaimAnalysis,
} from "@praviar/shared-types";

// Mock the ClaimElementRow component since it has its own complex interactions
vi.mock("@/components/patent/claim-element-row", () => ({
  ClaimElementRow: ({ element }: any) => (
    <div data-testid={`claim-element-${element.element_number}`}>
      Element {element.element_number}: {element.status}
    </div>
  ),
}));

import { ClaimsTab } from "@/components/report/claims-tab";

describe("ClaimsTab reasoning display", () => {
  describe("renders claim reasoning text when present", () => {
    it("shows reasoning for Fictional Meridian claim 1", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      // Fictional Meridian claim 1 has reasoning text
      expect(
        screen.getByText(
          /Three of four elements are met\. The yield limitation/,
        ),
      ).toBeInTheDocument();
    });

    it("shows reasoning for Fictional Atlas claim 1", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      expect(
        screen.getByText(
          /Both key process elements.*acidification and crystallization.*are met/,
        ),
      ).toBeInTheDocument();
    });

    it("shows reasoning for Fictional Nova claim 1", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      expect(
        screen.getByText(
          /Neither element is met\. The evaluated process uses a completely different organism/,
        ),
      ).toBeInTheDocument();
    });

    it("renders reasoning in a bordered container", () => {
      const { container } = render(<ClaimsTab report={TEST_REPORT} />);

      // Reasoning blocks use border-l-2 class
      const reasoningBlocks = container.querySelectorAll(".border-l-2");
      expect(reasoningBlocks.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("does NOT render reasoning block when reasoning is empty", () => {
    it("does not render reasoning div when reasoning is empty string", () => {
      const claimNoReasoning: ClaimAnalysis = {
        claim_number: 1,
        claim_type: "independent",
        depends_on: null,
        preamble: "A test claim",
        transitional_phrase: "comprising",
        elements: [
          {
            element_number: 1,
            element_text: "Test element",
            status: "not_met",
            reasoning: "Element reasoning",
            confidence: 0.9,
            evidence: "Test evidence",
          },
        ],
        overall_status: "not_met",
        overall_confidence: 0.9,
        reasoning: "",
      };

      const patentNoReasoning: PatentAnalysis = {
        patent_id: "US99999999B2",
        title: "Test Patent",
        assignee: "Test Corp",
        expiry_date: "2040-01-01",
        claims_analyzed: [claimNoReasoning],
        risk_level: "low",
        risk_summary: "Test summary",
        design_around_suggestions: [],
        orange_book_info: null,
        model_used: "test-model",
        thinking_text: "",
        input_tokens: 100,
        output_tokens: 50,
      };

      const reportNoReasoning: FTOReport = {
        ...TEST_REPORT,
        patent_analyses: [patentNoReasoning],
      };

      const { container } = render(<ClaimsTab report={reportNoReasoning} />);

      // With empty reasoning, no border-l-2 reasoning block should be present
      const reasoningBlocks = container.querySelectorAll(".border-l-2");
      expect(reasoningBlocks.length).toBe(0);
    });

    it("does not render reasoning div when reasoning is undefined/null", () => {
      const claimNullReasoning: ClaimAnalysis = {
        claim_number: 1,
        claim_type: "independent",
        depends_on: null,
        preamble: "A test claim",
        transitional_phrase: "comprising",
        elements: [],
        overall_status: "not_met",
        overall_confidence: 0.9,
        reasoning: undefined as unknown as string,
      };

      const patentNullReasoning: PatentAnalysis = {
        patent_id: "US88888888B2",
        title: "Another Test Patent",
        assignee: "Another Corp",
        expiry_date: "2040-01-01",
        claims_analyzed: [claimNullReasoning],
        risk_level: "low",
        risk_summary: "Test summary",
        design_around_suggestions: [],
        orange_book_info: null,
        model_used: "test-model",
        thinking_text: "",
        input_tokens: 100,
        output_tokens: 50,
      };

      const reportNullReasoning: FTOReport = {
        ...TEST_REPORT,
        patent_analyses: [patentNullReasoning],
      };

      const { container } = render(<ClaimsTab report={reportNullReasoning} />);

      const reasoningBlocks = container.querySelectorAll(".border-l-2");
      expect(reasoningBlocks.length).toBe(0);
    });
  });

  describe("claims tab structure", () => {
    it("renders patent IDs", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      expect(screen.getAllByText("US0000000001A1").length).toBeGreaterThan(0);
      expect(screen.getAllByText("US0000000002A1").length).toBeGreaterThan(0);
      expect(screen.getAllByText("US0000000003A1").length).toBeGreaterThan(0);
      expect(screen.getAllByText("US0000000013A1").length).toBeGreaterThan(0);
      expect(screen.getAllByText("US0000000012A1").length).toBeGreaterThan(0);
    });

    it("renders claim numbers", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      // Multiple patents have Claim 1, so use getAllByText
      const claim1Elements = screen.getAllByText("Claim 1");
      expect(claim1Elements.length).toBeGreaterThanOrEqual(1);
    });

    it("renders claim types", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      const independentBadges = screen.getAllByText("independent");
      expect(independentBadges.length).toBeGreaterThanOrEqual(1);

      const dependentBadges = screen.getAllByText("dependent");
      expect(dependentBadges.length).toBeGreaterThanOrEqual(1);
    });

    it("renders claim status labels", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      // Multiple claims should show various statuses
      const partialLabels = screen.getAllByText("Partial");
      expect(partialLabels.length).toBeGreaterThanOrEqual(1);

      const notMetLabels = screen.getAllByText("Not Met");
      expect(notMetLabels.length).toBeGreaterThanOrEqual(1);
    });

    it("renders preamble text", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      expect(
        screen.getByText("A method for producing a C4 dicarboxylic acid"),
      ).toBeInTheDocument();
    });

    it("renders transitional phrase badges", () => {
      render(<ClaimsTab report={TEST_REPORT} />);

      const comprisingBadges = screen.getAllByText("comprising");
      expect(comprisingBadges.length).toBeGreaterThanOrEqual(1);
    });

    it("shows empty state when no patent analyses", () => {
      const reportEmpty: FTOReport = {
        ...TEST_REPORT,
        patent_analyses: [],
      };

      render(<ClaimsTab report={reportEmpty} />);

      expect(
        screen.getByText("No claim analyses available."),
      ).toBeInTheDocument();
    });
  });
});
