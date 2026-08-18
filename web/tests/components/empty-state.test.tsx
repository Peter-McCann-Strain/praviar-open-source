import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { EmptyState } from "@/components/shared/empty-state";
import { FileText, Search } from "lucide-react";

describe("EmptyState", () => {
  describe("basic rendering", () => {
    it("renders the title", () => {
      render(
        <EmptyState
          icon={FileText}
          title="No Analyses Yet"
          description="Start by running your first FTO analysis."
        />,
      );

      expect(screen.getByText("No Analyses Yet")).toBeInTheDocument();
    });

    it("renders the description", () => {
      render(
        <EmptyState
          icon={FileText}
          title="No Analyses Yet"
          description="Start by running your first FTO analysis."
        />,
      );

      expect(
        screen.getByText("Start by running your first FTO analysis."),
      ).toBeInTheDocument();
    });

    it("renders the icon", () => {
      const { container } = render(
        <EmptyState
          icon={Search}
          title="No Results"
          description="Try a different query."
        />,
      );

      // Lucide icons render as SVGs
      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
    });

    it("renders the canonical Praviar recovery mark", () => {
      const { container } = render(
        <EmptyState
          icon={Search}
          title="No Results"
          description="Try a different query."
        />,
      );

      expect(
        container.querySelector(
          'svg[data-praviar-mark="praviar-evidence-mark"]',
        ),
      ).toBeInTheDocument();
    });

    it("uses the operational field for full empty states", () => {
      render(
        <EmptyState
          icon={Search}
          title="No Results"
          description="Try a different query."
        />,
      );

      expect(screen.getByLabelText("No Results")).toHaveClass(
        "praviar-operational-field",
      );
      expect(screen.getByLabelText("No Results")).not.toHaveClass(
        "praviar-report-decision-field",
      );
    });
  });

  describe("action button", () => {
    it("renders action button when action is provided", () => {
      render(
        <EmptyState
          icon={FileText}
          title="No Analyses"
          description="Get started."
          action={{ label: "New Analysis", href: "/analyses/new" }}
        />,
      );

      expect(screen.getByText("New Analysis")).toBeInTheDocument();
    });

    it("renders action as a link with correct href", () => {
      render(
        <EmptyState
          icon={FileText}
          title="No Analyses"
          description="Get started."
          action={{ label: "New Analysis", href: "/analyses/new" }}
        />,
      );

      const link = screen.getByRole("link");
      expect(link).toHaveAttribute("href", "/analyses/new");
    });

    it("does not render action button when action is not provided", () => {
      render(
        <EmptyState
          icon={FileText}
          title="No Analyses"
          description="Get started."
        />,
      );

      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    });
  });

  describe("examples", () => {
    it("renders example buttons when examples are provided", () => {
      const examples = [
        { label: "Aspirin", value: "aspirin" },
        { label: "Succinic Acid", value: "succinic acid" },
      ];

      render(
        <EmptyState
          icon={FileText}
          title="No Analyses"
          description="Get started."
          examples={examples}
        />,
      );

      expect(screen.getByText("Aspirin")).toBeInTheDocument();
      expect(screen.getByText("Succinic Acid")).toBeInTheDocument();
    });

    it("renders the 'Try an example' label when examples are provided", () => {
      const examples = [{ label: "Aspirin", value: "aspirin" }];

      render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Test desc."
          examples={examples}
        />,
      );

      expect(screen.getByText("Try an example")).toBeInTheDocument();
    });

    it("does not render examples section when examples array is empty", () => {
      render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Test desc."
          examples={[]}
        />,
      );

      expect(screen.queryByText("Try an example")).not.toBeInTheDocument();
    });

    it("does not render examples section when not provided", () => {
      render(
        <EmptyState icon={FileText} title="Test" description="Test desc." />,
      );

      expect(screen.queryByText("Try an example")).not.toBeInTheDocument();
    });

    it("calls onExampleClick when an example button is clicked", () => {
      const onExampleClick = vi.fn();
      const examples = [{ label: "Aspirin", value: "aspirin" }];

      render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Test desc."
          examples={examples}
          onExampleClick={onExampleClick}
        />,
      );

      fireEvent.click(screen.getByText("Aspirin"));

      expect(onExampleClick).toHaveBeenCalledWith("aspirin");
    });

    it("calls onExampleClick with the correct value for each example", () => {
      const onExampleClick = vi.fn();
      const examples = [
        { label: "Aspirin", value: "aspirin" },
        { label: "Ibuprofen", value: "ibuprofen" },
      ];

      render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Test desc."
          examples={examples}
          onExampleClick={onExampleClick}
        />,
      );

      fireEvent.click(screen.getByText("Ibuprofen"));

      expect(onExampleClick).toHaveBeenCalledWith("ibuprofen");
    });
  });

  describe("className", () => {
    it("applies custom className", () => {
      const { container } = render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Test desc."
          className="my-custom-class"
        />,
      );

      const wrapper = container.firstElementChild;
      expect(wrapper?.classList.contains("my-custom-class")).toBe(true);
    });
  });

  describe("additional edge cases", () => {
    it("renders title as an h3 heading element", () => {
      render(
        <EmptyState
          icon={FileText}
          title="No Compounds"
          description="Nothing found."
        />,
      );

      const heading = screen.getByRole("heading", { level: 3 });
      expect(heading).toHaveTextContent("No Compounds");
    });

    it("can promote route-level empty states to a page heading", () => {
      render(
        <EmptyState
          icon={FileText}
          title="This workspace page does not exist"
          description="Return to the dashboard."
          headingLevel={1}
        />,
      );

      expect(
        screen.getByRole("heading", {
          level: 1,
          name: "This workspace page does not exist",
        }),
      ).toBeInTheDocument();
    });

    it("renders context facts as practical recovery chips", () => {
      render(
        <EmptyState
          icon={FileText}
          title="No Compounds"
          description="Nothing found."
          contextItems={[
            "No private records exposed",
            "Filters can recover",
            "Workspace remains available",
          ]}
        />,
      );

      expect(
        screen.getByText("No private records exposed"),
      ).toBeInTheDocument();
      expect(screen.getByText("Filters can recover")).toBeInTheDocument();
      expect(
        screen.getByText("Workspace remains available"),
      ).toBeInTheDocument();
    });

    it("renders both action and examples together", () => {
      const onExampleClick = vi.fn();
      const examples = [{ label: "Aspirin", value: "aspirin" }];

      render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Desc."
          action={{ label: "Create", href: "/create" }}
          examples={examples}
          onExampleClick={onExampleClick}
        />,
      );

      expect(screen.getByText("Create")).toBeInTheDocument();
      expect(screen.getByText("Aspirin")).toBeInTheDocument();
      expect(screen.getByText("Try an example")).toBeInTheDocument();
    });

    it("does not throw when example is clicked without onExampleClick handler", () => {
      const examples = [{ label: "ExampleBtn", value: "test" }];

      render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Desc."
          examples={examples}
        />,
      );

      // Should not throw when clicking without handler — optional chaining handles it
      expect(() => {
        fireEvent.click(screen.getByText("ExampleBtn"));
      }).not.toThrow();
    });

    it("renders multiple example buttons in the flex container", () => {
      const examples = [
        { label: "A", value: "a" },
        { label: "B", value: "b" },
        { label: "C", value: "c" },
      ];

      render(
        <EmptyState
          icon={FileText}
          title="Test"
          description="Desc."
          examples={examples}
        />,
      );

      expect(screen.getByText("A")).toBeInTheDocument();
      expect(screen.getByText("B")).toBeInTheDocument();
      expect(screen.getByText("C")).toBeInTheDocument();
    });
  });
});
