import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Breadcrumb } from "@/components/shared/breadcrumb";

describe("Breadcrumb", () => {
  const items = [
    { label: "Dashboard", href: "/dashboard" },
    { label: "Analyses", href: "/analyses" },
    { label: "FTO-2026-001" },
  ];

  it("renders all breadcrumb items", () => {
    render(<Breadcrumb items={items} />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Analyses")).toBeInTheDocument();
    expect(screen.getByText("FTO-2026-001")).toBeInTheDocument();
  });

  it("renders nav with aria-label", () => {
    const { container } = render(<Breadcrumb items={items} />);
    const nav = container.querySelector('nav[aria-label="Breadcrumb"]');
    expect(nav).toBeInTheDocument();
  });

  it("marks last item with aria-current=page", () => {
    render(<Breadcrumb items={items} />);
    const current = screen.getByTitle("FTO-2026-001");
    expect(current).toHaveAttribute("aria-current", "page");
  });

  it("renders links for items with href", () => {
    render(<Breadcrumb items={items} />);
    const link = screen.getByTitle("Dashboard");
    expect(link).toHaveAttribute("href", "/dashboard");
    expect(link).toHaveClass("min-h-11", "focus-visible:ring-brand-primary/70");
  });

  it("does not render link for last item", () => {
    render(<Breadcrumb items={items} />);
    const current = screen.getByTitle("FTO-2026-001");
    expect(current.closest("a")).toBeNull();
    expect(current).toHaveClass("min-h-11");
  });

  it("renders chevron separators between items", () => {
    const { container } = render(<Breadcrumb items={items} />);
    const chevrons = container.querySelectorAll("svg");
    expect(chevrons.length).toBe(2);
  });

  it("gives the intermediate label room and ellipsizes text inside its flex item", () => {
    const { container } = render(<Breadcrumb items={items} />);
    const nav = container.querySelector('nav[aria-label="Breadcrumb"]');
    const list = nav?.querySelector("ol");

    expect(nav).toHaveClass("overflow-x-auto", "overscroll-x-contain");
    expect(list).toHaveClass("flex-nowrap", "w-full", "min-w-0");
    expect(list?.children[0]).toHaveClass("shrink-0");
    expect(list?.children[1]).toHaveClass("flex-1", "min-w-0");
    expect(list?.children[2]).toHaveClass("shrink-0", "min-w-0");
    expect(screen.getByText("FTO-2026-001")).toHaveClass(
      "overflow-hidden",
      "text-ellipsis",
      "whitespace-nowrap",
    );
  });

  it("ellipsizes a long current page without shortening its accessible text", () => {
    const longLabel = "Example Molecule Alpha — retrieval replay";
    const { container } = render(
      <Breadcrumb
        items={[{ label: "Analyses", href: "/analyses" }, { label: longLabel }]}
      />,
    );

    const list = container.querySelector("ol");
    const currentPage = screen.getByTitle(longLabel);
    const visibleLabel = screen.getByText(longLabel);

    expect(list?.children[1]).toHaveClass("flex-1", "min-w-0");
    expect(currentPage).toHaveAttribute("aria-current", "page");
    expect(currentPage).toHaveAttribute("title", longLabel);
    expect(currentPage).toHaveTextContent(longLabel);
    expect(currentPage).toHaveClass("w-full", "min-w-0", "overflow-hidden");
    expect(visibleLabel).toHaveClass(
      "w-full",
      "max-w-full",
      "overflow-hidden",
      "text-ellipsis",
      "whitespace-nowrap",
    );
  });
});
