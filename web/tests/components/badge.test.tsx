import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "@/components/ui/badge";

describe("Badge", () => {
  describe("rendering", () => {
    it("renders children text", () => {
      render(<Badge>Active</Badge>);
      expect(screen.getByText("Active")).toBeInTheDocument();
    });

    it("renders as a div element", () => {
      const { container } = render(<Badge>Tag</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.tagName).toBe("DIV");
    });
  });

  describe("variants", () => {
    it("applies default variant classes", () => {
      const { container } = render(<Badge variant="default">Default</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("border-brand-primary/25");
      expect(badge.className).toContain("bg-brand-primary/10");
      expect(badge.className).toContain("text-brand-primary");
    });

    it("applies secondary variant classes", () => {
      const { container } = render(
        <Badge variant="secondary">Secondary</Badge>,
      );
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("border-[var(--border-default)]");
      expect(badge.className).toContain("bg-[var(--surface-active)]");
      expect(badge.className).toContain("text-[var(--text-secondary)]");
    });

    it("applies destructive variant classes", () => {
      const { container } = render(<Badge variant="destructive">Error</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("border-error/25");
      expect(badge.className).toContain("bg-error/10");
      expect(badge.className).toContain("text-[var(--color-error-badge-fg)]");
    });

    it("applies warning variant classes", () => {
      const { container } = render(<Badge variant="warning">Warning</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("border-warning/25");
      expect(badge.className).toContain("bg-warning/10");
      expect(badge.className).toContain("text-warning");
    });

    it("applies success variant classes", () => {
      const { container } = render(<Badge variant="success">Passed</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("border-success/25");
      expect(badge.className).toContain("bg-success/10");
      expect(badge.className).toContain("text-success");
    });

    it("applies outline variant classes", () => {
      const { container } = render(<Badge variant="outline">Outline</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("border-[var(--border-emphasis)]");
      expect(badge.className).toContain("text-[var(--text-secondary)]");
    });

    it("uses default variant when none specified", () => {
      const { container } = render(<Badge>No variant</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("bg-brand-primary/10");
      expect(badge.className).toContain("text-brand-primary");
    });
  });

  describe("className prop", () => {
    it("passes custom className", () => {
      const { container } = render(<Badge className="my-badge">Custom</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("my-badge");
    });

    it("merges custom className with variant classes", () => {
      const { container } = render(
        <Badge variant="success" className="extra">
          Success
        </Badge>,
      );
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("extra");
      expect(badge.className).toContain("bg-success/10");
    });
  });

  describe("base styling", () => {
    it("includes base utility classes", () => {
      const { container } = render(<Badge>Base</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("inline-flex");
      expect(badge.className).toContain("items-center");
      expect(badge.className).toContain("rounded-full");
      expect(badge.className).toContain("border");
      expect(badge.className).toContain("text-xs");
      expect(badge.className).toContain("font-semibold");
    });

    it("includes padding classes", () => {
      const { container } = render(<Badge>Padded</Badge>);
      const badge = container.firstElementChild!;
      expect(badge.className).toContain("px-2.5");
      expect(badge.className).toContain("py-0.5");
    });
  });

  describe("HTML attributes pass-through", () => {
    it("supports data-testid", () => {
      render(<Badge data-testid="my-badge">Test</Badge>);
      expect(screen.getByTestId("my-badge")).toBeInTheDocument();
    });

    it("supports role attribute", () => {
      render(<Badge role="status">Status</Badge>);
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });
});
