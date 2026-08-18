import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageTransition } from "@/components/shared/page-transition";

describe("PageTransition", () => {
  it("renders a stable transition wrapper", () => {
    const { container } = render(
      <PageTransition>
        <main>Dashboard content</main>
      </PageTransition>,
    );

    expect(screen.getByText("Dashboard content")).toBeInTheDocument();
    expect(container.firstElementChild?.tagName).toBe("DIV");
    expect(container.firstElementChild).toHaveClass("animate-fade-up");
    expect(container.firstElementChild).toHaveAttribute(
      "data-praviar-page-transition",
    );
  });
});
