import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "@/components/shared/status-badge";

describe("StatusBadge", () => {
  describe("text rendering", () => {
    it("capitalizes the first letter of the status", () => {
      render(<StatusBadge status="pending" />);
      expect(screen.getByText("Pending")).toBeInTheDocument();
    });

    it("renders Running for running status", () => {
      render(<StatusBadge status="running" />);
      expect(screen.getByText("Running")).toBeInTheDocument();
    });

    it("renders Completed for completed status", () => {
      render(<StatusBadge status="completed" />);
      expect(screen.getByText("Completed")).toBeInTheDocument();
    });

    it("renders Failed for failed status", () => {
      render(<StatusBadge status="failed" />);
      expect(screen.getByText("Failed")).toBeInTheDocument();
    });

    it("renders Cancelled for cancelled status", () => {
      render(<StatusBadge status="cancelled" />);
      expect(screen.getByText("Cancelled")).toBeInTheDocument();
    });
  });

  describe("status-specific classes", () => {
    it("applies pending styles with semantic tokens", () => {
      const { container } = render(<StatusBadge status="pending" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-[var(--surface-active)]");
      expect(badge?.className).toContain("border-[var(--border-default)]");
    });

    it("applies running styles with animate-pulse", () => {
      const { container } = render(<StatusBadge status="running" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-info/15");
      expect(badge?.className).toContain("text-[var(--text-primary)]");
      expect(badge?.className).toContain("border-info/25");
      expect(badge?.className).toContain("animate-pulse");
    });

    it("applies completed styles", () => {
      const { container } = render(<StatusBadge status="completed" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-success/15");
      expect(badge?.className).toContain(
        "text-[var(--color-success-badge-fg)]",
      );
      expect(badge?.className).toContain("border-success/25");
    });

    it("applies failed styles", () => {
      const { container } = render(<StatusBadge status="failed" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-error/15");
      expect(badge?.className).toContain("text-[var(--color-error-badge-fg)]");
      expect(badge?.className).toContain("border-error/25");
    });

    it("applies cancelled styles with semantic tokens", () => {
      const { container } = render(<StatusBadge status="cancelled" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-[var(--surface-active)]");
      expect(badge?.className).toContain("border-[var(--border-default)]");
    });
  });

  describe("unknown status", () => {
    it("falls back to pending styles for unknown status", () => {
      const { container } = render(<StatusBadge status="unknown" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("bg-[var(--surface-active)]");
      expect(badge?.className).toContain("border-[var(--border-default)]");
    });

    it("still renders the unknown status text capitalized", () => {
      render(<StatusBadge status="unknown" />);
      expect(screen.getByText("Unknown")).toBeInTheDocument();
    });
  });

  describe("base styling", () => {
    it("includes base utility classes", () => {
      const { container } = render(<StatusBadge status="pending" />);
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("rounded-full");
      expect(badge?.className).toContain("border");
      expect(badge?.className).toContain("text-xs");
      expect(badge?.className).toContain("font-medium");
    });
  });

  describe("className prop", () => {
    it("applies additional className", () => {
      const { container } = render(
        <StatusBadge status="completed" className="extra-class" />,
      );
      const badge = container.querySelector("span");
      expect(badge?.className).toContain("extra-class");
    });
  });

  describe("running status does not share animate-pulse with others", () => {
    it("pending does not have animate-pulse", () => {
      const { container } = render(<StatusBadge status="pending" />);
      const badge = container.querySelector("span");
      expect(badge?.className).not.toContain("animate-pulse");
    });

    it("completed does not have animate-pulse", () => {
      const { container } = render(<StatusBadge status="completed" />);
      const badge = container.querySelector("span");
      expect(badge?.className).not.toContain("animate-pulse");
    });

    it("failed does not have animate-pulse", () => {
      const { container } = render(<StatusBadge status="failed" />);
      const badge = container.querySelector("span");
      expect(badge?.className).not.toContain("animate-pulse");
    });
  });
});
