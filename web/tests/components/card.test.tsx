import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";

describe("Card", () => {
  describe("Card component", () => {
    it("renders children", () => {
      render(<Card>Card content</Card>);
      expect(screen.getByText("Card content")).toBeInTheDocument();
    });

    it("renders as a div element", () => {
      const { container } = render(<Card>Content</Card>);
      const card = container.firstElementChild!;
      expect(card.tagName).toBe("DIV");
    });

    it("applies base styling classes", () => {
      const { container } = render(<Card>Content</Card>);
      const card = container.firstElementChild!;
      expect(card.className).toContain("rounded-lg");
      expect(card.className).toContain("border");
      expect(card.className).toContain("praviar-surface-premium");
      expect(card.className).toContain("border-[var(--card-border)]");
    });

    it("passes custom className", () => {
      const { container } = render(<Card className="my-card">Content</Card>);
      const card = container.firstElementChild!;
      expect(card.className).toContain("my-card");
      expect(card.className).toContain("rounded-lg");
    });

    it("forwards additional HTML attributes", () => {
      render(
        <Card data-testid="test-card" role="region">
          Content
        </Card>,
      );
      expect(screen.getByTestId("test-card")).toBeInTheDocument();
      expect(screen.getByRole("region")).toBeInTheDocument();
    });
  });

  describe("CardHeader component", () => {
    it("renders children", () => {
      render(<CardHeader>Header content</CardHeader>);
      expect(screen.getByText("Header content")).toBeInTheDocument();
    });

    it("applies header padding", () => {
      const { container } = render(<CardHeader>Header</CardHeader>);
      const header = container.firstElementChild!;
      expect(header.className).toContain("p-6");
    });

    it("passes custom className", () => {
      const { container } = render(
        <CardHeader className="custom-header">Header</CardHeader>,
      );
      const header = container.firstElementChild!;
      expect(header.className).toContain("custom-header");
    });
  });

  describe("CardTitle component", () => {
    it("renders children", () => {
      render(<CardTitle>My Title</CardTitle>);
      expect(screen.getByText("My Title")).toBeInTheDocument();
    });

    it("participates in the screen-reader heading tree by default", () => {
      render(<CardTitle>My Title</CardTitle>);
      expect(
        screen.getByRole("heading", { name: "My Title", level: 3 }),
      ).toBeInTheDocument();
    });

    it("allows callers to override the heading level", () => {
      render(<CardTitle aria-level={2}>Section Title</CardTitle>);
      expect(
        screen.getByRole("heading", { name: "Section Title", level: 2 }),
      ).toBeInTheDocument();
    });

    it("applies title styling", () => {
      const { container } = render(<CardTitle>Title</CardTitle>);
      const title = container.firstElementChild!;
      // type-heading-md bundles font-size + font-weight (600/semibold) as a composite token
      expect(title.className).toContain("type-heading-md");
      expect(title.className).toContain("text-[var(--text-primary)]");
    });

    it("passes custom className", () => {
      const { container } = render(
        <CardTitle className="custom-title">Title</CardTitle>,
      );
      const title = container.firstElementChild!;
      expect(title.className).toContain("custom-title");
    });
  });

  describe("CardDescription component", () => {
    it("renders children", () => {
      render(<CardDescription>A description</CardDescription>);
      expect(screen.getByText("A description")).toBeInTheDocument();
    });

    it("applies description styling", () => {
      const { container } = render(<CardDescription>Desc</CardDescription>);
      const desc = container.firstElementChild!;
      expect(desc.className).toContain("text-sm");
      expect(desc.className).toContain("text-[var(--text-secondary)]");
    });

    it("passes custom className", () => {
      const { container } = render(
        <CardDescription className="custom-desc">Desc</CardDescription>,
      );
      const desc = container.firstElementChild!;
      expect(desc.className).toContain("custom-desc");
    });
  });

  describe("CardContent component", () => {
    it("renders children", () => {
      render(<CardContent>Body text</CardContent>);
      expect(screen.getByText("Body text")).toBeInTheDocument();
    });

    it("applies content padding", () => {
      const { container } = render(<CardContent>Content</CardContent>);
      const content = container.firstElementChild!;
      expect(content.className).toContain("p-6");
      expect(content.className).toContain("pt-0");
    });

    it("passes custom className", () => {
      const { container } = render(
        <CardContent className="custom-content">Content</CardContent>,
      );
      const content = container.firstElementChild!;
      expect(content.className).toContain("custom-content");
    });
  });

  describe("composite usage", () => {
    it("renders a full card with all sub-components", () => {
      render(
        <Card data-testid="full-card">
          <CardHeader>
            <CardTitle>Analysis Report</CardTitle>
            <CardDescription>FTO analysis for aspirin</CardDescription>
          </CardHeader>
          <CardContent>
            <p>Risk level: High</p>
          </CardContent>
        </Card>,
      );

      expect(screen.getByTestId("full-card")).toBeInTheDocument();
      expect(screen.getByText("Analysis Report")).toBeInTheDocument();
      expect(screen.getByText("FTO analysis for aspirin")).toBeInTheDocument();
      expect(screen.getByText("Risk level: High")).toBeInTheDocument();
    });

    it("nests sub-components correctly in the DOM", () => {
      const { container } = render(
        <Card>
          <CardHeader>
            <CardTitle>Title</CardTitle>
          </CardHeader>
          <CardContent>Body</CardContent>
        </Card>,
      );

      const card = container.firstElementChild!;
      // Card should have two direct children: CardHeader and CardContent
      expect(card.children).toHaveLength(2);
      // CardHeader contains CardTitle
      expect(card.children[0].textContent).toContain("Title");
      // CardContent contains body text
      expect(card.children[1].textContent).toContain("Body");
    });
  });
});
