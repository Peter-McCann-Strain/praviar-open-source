import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DashboardNotFound from "@/app/(dashboard)/not-found";

describe("DashboardNotFound", () => {
  it("renders a branded, recoverable workspace not-found state", () => {
    const { container } = render(<DashboardNotFound />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "This workspace page does not exist",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).toBeInTheDocument();
    expect(screen.getByText("No private records exposed")).toBeInTheDocument();
    expect(screen.getByText("Navigation can recover")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to Dashboard" }),
    ).toHaveAttribute("href", "/dashboard");
  });
});
