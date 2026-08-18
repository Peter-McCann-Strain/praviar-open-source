import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RiskBadge } from "@/components/shared/risk-badge";

describe("RiskBadge", () => {
  describe("text rendering", () => {
    it("renders risk text in uppercase", () => {
      render(<RiskBadge risk="high" />);
      expect(screen.getByText("HIGH")).toBeInTheDocument();
    });

    it("uppercases lowercase input", () => {
      render(<RiskBadge risk="medium" />);
      expect(screen.getByText("MEDIUM")).toBeInTheDocument();
    });

    it("uppercases mixed-case input", () => {
      render(<RiskBadge risk="Low" />);
      expect(screen.getByText("LOW")).toBeInTheDocument();
    });

    it("renders clear risk text", () => {
      render(<RiskBadge risk="clear" />);
      expect(screen.getByText("CLEAR")).toBeInTheDocument();
    });
  });

  describe("color classes for each risk level", () => {
    it("applies red color classes for high risk", () => {
      const { container } = render(<RiskBadge risk="high" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-error/15");
      expect(badge?.className).toContain("text-[var(--color-error-badge-fg)]");
      expect(badge?.className).toContain("border-error/30");
    });

    it("applies amber color classes for medium risk", () => {
      const { container } = render(<RiskBadge risk="medium" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-warning/15");
      expect(badge?.className).toContain(
        "text-[var(--color-warning-badge-fg)]",
      );
      expect(badge?.className).toContain("border-warning/30");
    });

    it("applies emerald color classes for low risk", () => {
      const { container } = render(<RiskBadge risk="low" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-success/15");
      expect(badge?.className).toContain(
        "text-[var(--color-success-badge-fg)]",
      );
      expect(badge?.className).toContain("border-success/30");
    });

    it("applies blue color classes for clear risk", () => {
      const { container } = render(<RiskBadge risk="clear" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-info/15");
      expect(badge?.className).toContain("text-[var(--color-info-badge-fg)]");
      expect(badge?.className).toContain("border-info/30");
    });
  });

  describe("unknown risk level", () => {
    it("uses neutral review colors for unknown risk", () => {
      const { container } = render(<RiskBadge risk="unknown" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-[var(--surface-active)]");
      expect(badge?.className).toContain("text-[var(--text-secondary)]");
      expect(badge?.className).toContain("border-[var(--border-default)]");
      expect(badge?.className).not.toContain("bg-info/15");
    });

    it("still renders the unknown risk text uppercased", () => {
      render(<RiskBadge risk="unknown" />);
      expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
    });

    it("uses neutral review colors for empty string", () => {
      const { container } = render(<RiskBadge risk="" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-[var(--surface-active)]");
      expect(badge?.className).not.toContain("bg-info/15");
    });
  });

  describe("size variants", () => {
    it("applies sm size classes", () => {
      const { container } = render(<RiskBadge risk="high" size="sm" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("px-2");
      expect(badge?.className).toContain("py-0.5");
      expect(badge?.className).toContain("text-xs");
    });

    it("applies md size classes by default", () => {
      const { container } = render(<RiskBadge risk="high" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("px-2.5");
      expect(badge?.className).toContain("text-xs");
    });

    it("applies lg size classes", () => {
      const { container } = render(<RiskBadge risk="high" size="lg" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("px-3.5");
      expect(badge?.className).toContain("py-1.5");
      expect(badge?.className).toContain("text-sm");
      expect(badge?.className).toContain("font-bold");
    });
  });

  describe("animated prop", () => {
    it("does not include animate-pulse by default", () => {
      const { container } = render(<RiskBadge risk="high" />);
      const badge = container.querySelector("span");
      expect(badge?.className).not.toContain("animate-pulse");
    });

    it("uses static emphasis when animated is true", () => {
      const { container } = render(<RiskBadge risk="high" animated />);
      const badge = container.querySelector("span");
      expect(badge?.className).not.toContain("animate-pulse");
      expect(badge?.className).toContain("ring-2");
      expect(badge?.className).toContain("ring-current/10");
    });
  });

  describe("className prop", () => {
    it("applies additional className", () => {
      const { container } = render(
        <RiskBadge risk="high" className="my-custom" />,
      );
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("my-custom");
    });
  });

  describe("base styling", () => {
    it("includes base utility classes", () => {
      const { container } = render(<RiskBadge risk="high" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("rounded-full");
      expect(badge?.className).toContain("font-semibold");
      expect(badge?.className).toContain("uppercase");
      expect(badge?.className).toContain("tracking-wider");
    });
  });
});
