import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Mock error-logger before importing the component
vi.mock("@/lib/error-logger", () => ({
  logError: vi.fn(),
}));

// Mock lucide-react icons to simple spans
vi.mock("lucide-react", () => ({
  AlertTriangle: (props: any) => (
    <span data-testid="alert-triangle-icon" {...props} />
  ),
  RefreshCcw: (props: any) => (
    <span data-testid="refresh-ccw-icon" {...props} />
  ),
  Home: (props: any) => <span data-testid="home-icon" {...props} />,
  Loader2: (props: any) => <span data-testid="loader-icon" {...props} />,
}));

// Mock Button to render a real <button> (or delegate to child via asChild)
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, asChild, ...props }: any) => {
    if (asChild) {
      // Render children directly (the Link/anchor)
      return <>{children}</>;
    }
    return (
      <button onClick={onClick} {...props}>
        {children}
      </button>
    );
  },
}));

import { logError } from "@/lib/error-logger";
import RouteError from "@/app/(dashboard)/analyses/new/error";

describe("RouteError", () => {
  const mockReset = vi.fn();

  function makeError(
    message: string,
    digest?: string,
  ): Error & { digest?: string } {
    const err = new Error(message) as Error & { digest?: string };
    if (digest !== undefined) {
      err.digest = digest;
    }
    return err;
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a section-specific recovery heading", () => {
    render(<RouteError error={makeError("Test failure")} reset={mockReset} />);
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "New analysis temporarily unavailable",
      }),
    ).toBeInTheDocument();
  });

  it("shows standard recovery copy", () => {
    render(<RouteError error={makeError("")} reset={mockReset} />);
    expect(
      screen.getByText(
        "We could not load this workspace. The issue has been logged, and retrying will request a fresh view.",
      ),
    ).toBeInTheDocument();
  });

  it("does not expose the raw error message to the route UI", () => {
    render(
      <RouteError
        error={makeError("Database connection lost")}
        reset={mockReset}
      />,
    );
    expect(
      screen.queryByText("Database connection lost"),
    ).not.toBeInTheDocument();
  });

  it("displays error digest when present", () => {
    render(
      <RouteError
        error={makeError("Oops", "abc-123-digest")}
        reset={mockReset}
      />,
    );
    expect(screen.getByText(/Reference:/)).toBeInTheDocument();
    expect(screen.queryByText(/Reference: Ref:/)).not.toBeInTheDocument();
    expect(screen.getByText(/abc-123-digest/)).toBeInTheDocument();
  });

  it("does not show digest when not present", () => {
    render(<RouteError error={makeError("Oops")} reset={mockReset} />);
    expect(screen.queryByText(/Reference:/)).not.toBeInTheDocument();
  });

  it('"Try Again" button calls reset function on click', () => {
    render(<RouteError error={makeError("Oops")} reset={mockReset} />);
    const tryAgainButton = screen.getByRole("button", { name: /try again/i });
    fireEvent.click(tryAgainButton);
    expect(mockReset).toHaveBeenCalledTimes(1);
  });

  it('"Analyses" link has correct href', () => {
    render(<RouteError error={makeError("Oops")} reset={mockReset} />);
    const analysesLink = screen.getByRole("link", { name: /analyses/i });
    expect(analysesLink).toHaveAttribute("href", "/analyses");
  });

  it("calls logError on mount with the error", () => {
    const error = makeError("Mount error");
    render(<RouteError error={error} reset={mockReset} />);
    expect(logError).toHaveBeenCalledTimes(1);
    expect(logError).toHaveBeenCalledWith(error, {
      source: "New analysisErrorBoundary",
      extra: { digest: undefined },
    });
  });
});
