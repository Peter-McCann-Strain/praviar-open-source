import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LibraryStatusState } from "@/components/shared/library-status-state";

describe("LibraryStatusState", () => {
  it("renders patent access checking without exposing library data", () => {
    render(<LibraryStatusState surface="patents" variant="auth" />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Checking patent evidence library access",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No library data exposed")).toBeInTheDocument();
    expect(screen.getByText("Filters open after access")).toBeInTheDocument();
  });

  it("renders compound loading as a governed workspace state", () => {
    render(<LibraryStatusState surface="compounds" variant="loading" />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByTestId("compounds-library-status-loading"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Loading compound library",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Evidence index requested")).toBeInTheDocument();
    expect(screen.getByText("Search and filters wait")).toBeInTheDocument();
  });

  it("renders temporary failure with retry and no raw diagnostics", () => {
    const onRetry = vi.fn();
    render(
      <LibraryStatusState
        surface="patents"
        variant="temporary"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Patent evidence library temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No library data changed")).toBeInTheDocument();
    expect(
      screen.queryByText(/api error|database|bearer|org_id|select \*/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Keep patent filters and report links unchanged/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry library load" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
