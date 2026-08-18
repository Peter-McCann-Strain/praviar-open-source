import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RootError from "@/app/error";
import GlobalError from "@/app/global-error";
import { ErrorBoundary } from "@/components/shared/error-boundary";

vi.mock("@/lib/error-logger", () => ({
  logError: vi.fn(),
}));

function makeError(
  message: string,
  digest?: string,
): Error & { digest?: string } {
  const error = new Error(message) as Error & { digest?: string };
  if (digest) {
    error.digest = digest;
  }
  return error;
}

function ThrowingSection() {
  throw new Error("database password leaked through component crash");
}

describe("error boundary sanitization", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps the root error UI premium without exposing raw exception text", () => {
    const reset = vi.fn();

    const { container } = render(
      <RootError
        error={makeError("postgres://secret-token", "root-123")}
        reset={reset}
      />,
    );

    expect(container.querySelector("main#main-content")).toBeInTheDocument();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Praviar needs a refresh",
    );
    expect(
      screen.queryByText("postgres://secret-token"),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/Reference: root-123/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toHaveClass(
      "min-h-11",
    );

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("keeps the global broken-layout fallback sanitized", () => {
    const { container } = render(
      <GlobalError
        error={makeError("api key sk_live_secret", "postgres://secret-token")}
        reset={vi.fn()}
      />,
    );

    expect(container.querySelector("main#main-content")).toBeInTheDocument();

    expect(
      screen.getByRole("heading", { name: "Critical Application Error" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("api key sk_live_secret"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("postgres://secret-token"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Diagnostic context has been logged/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try Again" })).toHaveStyle({
      minHeight: "44px",
    });
    expect(screen.getByRole("link", { name: "Go Home" })).toHaveStyle({
      minHeight: "44px",
    });
  });

  it("keeps component crashes isolated without rendering raw error text", () => {
    render(
      <ErrorBoundary title="Summary failed to load">
        <ThrowingSection />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Summary failed to load",
    );
    expect(
      screen.queryByText("database password leaked through component crash"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Summary failed to load",
    );
  });
});
