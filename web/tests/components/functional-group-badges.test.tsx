import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FunctionalGroupBadges } from "@/components/chemistry/functional-group-badges";

describe("FunctionalGroupBadges", () => {
  describe("renders badges for each functional group", () => {
    it("renders one badge per group", () => {
      const groups = ["Hydroxyl", "Carboxyl", "Amine"];
      const { container } = render(<FunctionalGroupBadges groups={groups} />);
      const badges = container.querySelectorAll("span.inline-flex");
      expect(badges.length).toBe(3);
    });

    it("displays the group name text for each badge", () => {
      const groups = ["Hydroxyl", "Carboxyl", "Amine"];
      render(<FunctionalGroupBadges groups={groups} />);
      expect(screen.getByText("Hydroxyl")).toBeInTheDocument();
      expect(screen.getByText("Carboxyl")).toBeInTheDocument();
      expect(screen.getByText("Amine")).toBeInTheDocument();
    });

    it("renders a wrapper div with flex layout", () => {
      const { container } = render(
        <FunctionalGroupBadges groups={["Hydroxyl"]} />,
      );
      const wrapper = container.firstElementChild;
      expect(wrapper?.className).toContain("flex");
      expect(wrapper?.className).toContain("flex-wrap");
      expect(wrapper?.className).toContain("gap-1.5");
    });
  });

  describe("empty array returns null", () => {
    it("renders nothing when groups is an empty array", () => {
      const { container } = render(<FunctionalGroupBadges groups={[]} />);
      expect(container.innerHTML).toBe("");
    });

    it("does not render a wrapper div for empty groups", () => {
      const { container } = render(<FunctionalGroupBadges groups={[]} />);
      expect(container.firstElementChild).toBeNull();
    });
  });

  describe("color mapping for known groups", () => {
    it("applies blue classes for hydroxyl", () => {
      render(<FunctionalGroupBadges groups={["Hydroxyl"]} />);
      const badge = screen.getByText("Hydroxyl");
      expect(badge.className).toContain("bg-info/15");
      expect(badge.className).toContain("text-info-emphasis");
      expect(badge.className).toContain("border-info/25");
    });

    it("applies red classes for carboxyl", () => {
      render(<FunctionalGroupBadges groups={["Carboxyl"]} />);
      const badge = screen.getByText("Carboxyl");
      expect(badge.className).toContain("bg-error/15");
      expect(badge.className).toContain("text-error-emphasis");
      expect(badge.className).toContain("border-error/25");
    });

    it("applies info classes for amine", () => {
      render(<FunctionalGroupBadges groups={["Amine"]} />);
      const badge = screen.getByText("Amine");
      expect(badge.className).toContain("bg-info/15");
      expect(badge.className).toContain("text-info-emphasis");
      expect(badge.className).toContain("border-info/25");
    });

    it("applies info classes for ester", () => {
      render(<FunctionalGroupBadges groups={["Ester"]} />);
      const badge = screen.getByText("Ester");
      expect(badge.className).toContain("bg-info/15");
      expect(badge.className).toContain("text-info-emphasis");
      expect(badge.className).toContain("border-info/25");
    });

    it("applies warning classes for ketone", () => {
      render(<FunctionalGroupBadges groups={["Ketone"]} />);
      const badge = screen.getByText("Ketone");
      expect(badge.className).toContain("bg-warning/15");
      expect(badge.className).toContain("text-warning-emphasis");
      expect(badge.className).toContain("border-warning/25");
    });

    it("applies info classes for aromatic", () => {
      render(<FunctionalGroupBadges groups={["Aromatic"]} />);
      const badge = screen.getByText("Aromatic");
      expect(badge.className).toContain("bg-info/15");
      expect(badge.className).toContain("text-info-emphasis");
      expect(badge.className).toContain("border-info/25");
    });

    it("applies brand-primary classes for amide", () => {
      render(<FunctionalGroupBadges groups={["Amide"]} />);
      const badge = screen.getByText("Amide");
      expect(badge.className).toContain("bg-brand-primary/15");
      expect(badge.className).toContain("text-brand-primary-dim");
      expect(badge.className).toContain("border-brand-primary/25");
    });

    it("applies error classes for nitro", () => {
      render(<FunctionalGroupBadges groups={["Nitro"]} />);
      const badge = screen.getByText("Nitro");
      expect(badge.className).toContain("bg-error/15");
      expect(badge.className).toContain("text-error-emphasis");
      expect(badge.className).toContain("border-error/25");
    });
  });

  describe("case insensitivity in color lookup", () => {
    it("matches lowercase group names to colors", () => {
      render(<FunctionalGroupBadges groups={["hydroxyl"]} />);
      const badge = screen.getByText("hydroxyl");
      expect(badge.className).toContain("bg-info/15");
    });

    it("matches uppercase group names to colors", () => {
      render(<FunctionalGroupBadges groups={["CARBOXYL"]} />);
      const badge = screen.getByText("CARBOXYL");
      expect(badge.className).toContain("bg-error/15");
    });

    it("matches mixed-case group names to colors", () => {
      render(<FunctionalGroupBadges groups={["Amine"]} />);
      const badge = screen.getByText("Amine");
      expect(badge.className).toContain("bg-info/15");
    });
  });

  describe("unknown group falls back to default colors", () => {
    it("applies default styling for an unknown group", () => {
      render(<FunctionalGroupBadges groups={["Unknown Group"]} />);
      const badge = screen.getByText("Unknown Group");
      // Default color uses CSS vars
      expect(badge.className).toContain("bg-[var(--surface-active)]");
      expect(badge.className).toContain("text-[var(--text-secondary)]");
      expect(badge.className).toContain("border-[var(--border-emphasis)]");
    });

    it("strips non-alpha characters from group name for lookup", () => {
      // "Hydroxyl-Group" becomes "hydroxylgroup" which is not in the map
      render(<FunctionalGroupBadges groups={["Hydroxyl-Group"]} />);
      const badge = screen.getByText("Hydroxyl-Group");
      // Since "hydroxylgroup" is not a match, it falls back to default
      expect(badge.className).toContain("bg-[var(--surface-active)]");
    });
  });

  describe("base styling", () => {
    it("all badges have rounded-full class", () => {
      const groups = ["Hydroxyl", "Ester"];
      const { container } = render(<FunctionalGroupBadges groups={groups} />);
      const badges = container.querySelectorAll("span.inline-flex");
      for (const badge of badges) {
        expect(badge.className).toContain("rounded-full");
      }
    });

    it("all badges have border class", () => {
      const { container } = render(
        <FunctionalGroupBadges groups={["Hydroxyl", "Amine"]} />,
      );
      const badges = container.querySelectorAll("span.inline-flex");
      for (const badge of badges) {
        expect(badge.className).toContain("border");
      }
    });

    it("all badges have font-medium class", () => {
      const { container } = render(
        <FunctionalGroupBadges groups={["Ketone"]} />,
      );
      const badge = container.querySelector("span.inline-flex");
      expect(badge?.className).toContain("font-medium");
    });

    it("keeps all badges at the design-system caption minimum", () => {
      const { container } = render(
        <FunctionalGroupBadges groups={["Ether"]} />,
      );
      const badge = container.querySelector("span.inline-flex");
      expect(badge?.className).toContain("text-xs");
    });
  });

  describe("className prop", () => {
    it("applies additional className to wrapper", () => {
      const { container } = render(
        <FunctionalGroupBadges groups={["Hydroxyl"]} className="my-class" />,
      );
      const wrapper = container.firstElementChild;
      expect(wrapper?.className).toContain("my-class");
    });
  });

  describe("many groups", () => {
    it("renders all groups in a large list", () => {
      const groups = [
        "Hydroxyl",
        "Carboxyl",
        "Amine",
        "Amide",
        "Ester",
        "Ether",
        "Ketone",
        "Aldehyde",
        "Nitrile",
        "Nitro",
        "Sulfone",
        "Phosphate",
        "Halide",
        "Aromatic",
        "Alkene",
        "Alkyne",
      ];
      const { container } = render(<FunctionalGroupBadges groups={groups} />);
      const badges = container.querySelectorAll("span.inline-flex");
      expect(badges.length).toBe(16);
    });

    it("each known group gets its specific color class", () => {
      const groups = ["Hydroxyl", "Carboxyl", "Amine"];
      render(<FunctionalGroupBadges groups={groups} />);
      expect(screen.getByText("Hydroxyl").className).toContain("bg-info/15");
      expect(screen.getByText("Carboxyl").className).toContain("bg-error/15");
      expect(screen.getByText("Amine").className).toContain("bg-info/15");
    });
  });

  describe("single group", () => {
    it("renders a single badge", () => {
      const { container } = render(
        <FunctionalGroupBadges groups={["Alkyne"]} />,
      );
      const badges = container.querySelectorAll("span.inline-flex");
      expect(badges.length).toBe(1);
    });

    it("applies warning color for alkyne", () => {
      render(<FunctionalGroupBadges groups={["Alkyne"]} />);
      const badge = screen.getByText("Alkyne");
      expect(badge.className).toContain("bg-warning/15");
      expect(badge.className).toContain("text-warning-emphasis");
    });
  });
});
