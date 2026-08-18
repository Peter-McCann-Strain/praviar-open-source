import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WorkspaceBoundaryBanner } from "@/components/layout/workspace-boundary-banner";

describe("WorkspaceBoundaryBanner", () => {
  it("makes demo workspace data and legal boundary explicit", () => {
    render(<WorkspaceBoundaryBanner mode="demo" />);

    expect(
      screen.getByRole("complementary", {
        name: "Workspace data boundary",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Demo workspace")).toBeInTheDocument();
    expect(screen.getByText("Synthetic data visible")).toBeInTheDocument();
    expect(
      screen.getByText("Synthetic review data · not legal clearance."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not legal clearance opinions/i),
    ).toBeInTheDocument();
  });

  it("makes development auth bypass explicit", () => {
    render(<WorkspaceBoundaryBanner mode="dev-bypass" />);

    expect(screen.getByText("Development workspace")).toBeInTheDocument();
    expect(screen.getByText("Auth bypass active")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Auth bypass active · production sign-in still required.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/production authentication is still required/i),
    ).toBeInTheDocument();
  });
});
