import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RootNotFound from "@/app/not-found";

describe("RootNotFound", () => {
  it("renders a public-safe branded recovery state", () => {
    const { container } = render(<RootNotFound />);

    expect(container.querySelector("main#main-content")).toBeInTheDocument();

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "This Praviar page does not exist",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Public routes remain available"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to Praviar" }),
    ).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Back to Praviar" })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getByRole("link", { name: "View sample reports" }),
    ).toHaveAttribute("href", "/sample-reports");
    expect(screen.queryByText("404")).not.toBeInTheDocument();
  });
});
