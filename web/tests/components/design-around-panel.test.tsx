import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DesignAroundPanel } from "@/components/report/design-around-panel";
import { TEST_REPORT } from "../fixtures/report-fixture";
import type { FTOReport } from "@praviar/shared-types";

describe("DesignAroundPanel", () => {
  describe("renders nothing when no suggestions", () => {
    it("returns null when no patent analyses have design_around_suggestions", () => {
      const reportNoSuggestions: FTOReport = {
        ...TEST_REPORT,
        patent_analyses: TEST_REPORT.patent_analyses.map((pa) => ({
          ...pa,
          design_around_suggestions: [],
        })),
      };

      const { container } = render(
        <DesignAroundPanel report={reportNoSuggestions} />,
      );
      expect(container.innerHTML).toBe("");
    });

    it("returns null when only low/clear risk patents have suggestions", () => {
      const reportLowOnly: FTOReport = {
        ...TEST_REPORT,
        patent_analyses: TEST_REPORT.patent_analyses.map((pa) => ({
          ...pa,
          design_around_suggestions:
            pa.risk_level === "low" || pa.risk_level === "clear"
              ? [
                  {
                    element_avoided: 1,
                    suggestion: "Some suggestion",
                    feasibility: "High",
                  },
                ]
              : [],
        })),
      };

      const { container } = render(
        <DesignAroundPanel report={reportLowOnly} />,
      );
      expect(container.innerHTML).toBe("");
    });
  });

  describe("renders suggestions for high-risk patents", () => {
    it("shows suggestions for Fictional Meridian patent (US0000000001A1)", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(screen.getByText("US0000000001A1")).toBeInTheDocument();
    });

    it("renders two suggestions for Fictional Meridian patent", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Meridian patent has 2 design-around suggestions
      expect(
        screen.getByText(/Use a eukaryotic host organism/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Maintain production yields below 0.8 mol\/mol/),
      ).toBeInTheDocument();
    });

    it("shows suggestions for Fictional Atlas patent (US0000000002A1)", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(screen.getByText("US0000000002A1")).toBeInTheDocument();
    });
  });

  describe("renders suggestions for medium-risk patents", () => {
    it("shows suggestions for Fictional Nova patent (US0000000003A1)", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(screen.getByText("US0000000003A1")).toBeInTheDocument();
      expect(
        screen.getByText(/Ensure production pathway documentation/),
      ).toBeInTheDocument();
    });
  });

  describe("does NOT render suggestions for low or clear patents", () => {
    it("does not render Fictional Orbit patent (low risk)", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(screen.queryByText("US0000000013A1")).not.toBeInTheDocument();
    });

    it("does not render Fictional Myria patent (clear risk)", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(screen.queryByText("US0000000012A1")).not.toBeInTheDocument();
    });
  });

  describe("patent ID and title display", () => {
    it("shows patent ID in each group", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(screen.getByText("US0000000001A1")).toBeInTheDocument();
      expect(screen.getByText("US0000000002A1")).toBeInTheDocument();
      expect(screen.getByText("US0000000003A1")).toBeInTheDocument();
    });

    it("shows patent title in each group", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(
        screen.getByText(
          "Methods for producing C4 dicarboxylic acids using engineered prokaryotic microorganisms",
        ),
      ).toBeInTheDocument();
    });
  });

  describe("element avoided badge", () => {
    it("shows element_avoided number in badge text", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Multiple suggestions reference element 1 across patents, and Fictional Meridian has element 4
      const element1Badges = screen.getAllByText("Avoids Element 1");
      expect(element1Badges.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Avoids Element 4")).toBeInTheDocument();
    });
  });

  describe("feasibility text", () => {
    it("shows feasibility text for suggestions", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Meridian suggestion 1 feasibility
      expect(
        screen.getByText(/Moderate\. Yeast-based succinic acid production/),
      ).toBeInTheDocument();
    });

    it("shows High Feasibility label for high feasibility", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Atlas suggestion 1 has "High." feasibility, Fictional Nova suggestion also has "High."
      const highBadges = screen.getAllByText("High Feasibility");
      expect(highBadges.length).toBeGreaterThanOrEqual(1);
    });

    it("shows Moderate Feasibility label for moderate feasibility", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Meridian suggestion 1 has "Moderate." feasibility
      const moderateBadges = screen.getAllByText("Moderate Feasibility");
      expect(moderateBadges.length).toBeGreaterThanOrEqual(1);
    });

    it("shows Low Feasibility label for low feasibility", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Meridian suggestion 2 and Fictional Atlas suggestion 2 have "Low." feasibility
      const lowBadges = screen.getAllByText("Low Feasibility");
      expect(lowBadges.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("collapsible groups", () => {
    it("suggestions are visible by default (expanded)", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Suggestions should be visible by default
      expect(
        screen.getByText(/Use a eukaryotic host organism/),
      ).toBeInTheDocument();
    });

    it("clicking a group header toggles visibility", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Find the button for US0000000001A1 and click it to collapse
      const meridianButton = screen
        .getByText("US0000000001A1")
        .closest("button");
      expect(meridianButton).toBeTruthy();

      fireEvent.click(meridianButton!);

      // After collapse, the suggestion content should be hidden
      expect(
        screen.queryByText(/Use a eukaryotic host organism/),
      ).not.toBeInTheDocument();

      // Click again to expand
      fireEvent.click(meridianButton!);

      expect(
        screen.getByText(/Use a eukaryotic host organism/),
      ).toBeInTheDocument();
    });
  });

  describe("left border color matches feasibility", () => {
    it("applies emerald border for High feasibility", () => {
      const { container } = render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Atlas first suggestion or Fictional Nova suggestion has "High." feasibility
      const emeraldBorders = container.querySelectorAll(".border-l-success");
      expect(emeraldBorders.length).toBeGreaterThanOrEqual(1);
    });

    it("applies amber border for Moderate feasibility", () => {
      const { container } = render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Meridian first suggestion has "Moderate." feasibility
      const amberBorders = container.querySelectorAll(".border-l-warning");
      expect(amberBorders.length).toBeGreaterThanOrEqual(1);
    });

    it("applies red border for Low feasibility", () => {
      const { container } = render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Meridian second suggestion has "Low." feasibility
      const redBorders = container.querySelectorAll(".border-l-error");
      expect(redBorders.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("suggestion count badge", () => {
    it("shows total suggestion count in header", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      // Fictional Meridian: 2, Fictional Atlas: 2, Fictional Nova: 1 = 5 suggestions total
      expect(screen.getByText("5 suggestions")).toBeInTheDocument();
    });
  });

  describe("header", () => {
    it("shows Design-Around Strategies title", () => {
      render(<DesignAroundPanel report={TEST_REPORT} />);

      expect(screen.getByText("Design-Around Strategies")).toBeInTheDocument();
    });
  });
});
