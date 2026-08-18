import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppErrorState } from "@/components/shared/app-error-state";

describe("AppErrorState", () => {
  it("announces errors as labelled atomic alerts without raw backend details", () => {
    render(
      <AppErrorState
        title="Workspace temporarily unavailable"
        description="Retry when the workspace connection is available."
        detail={`postgres://secret-host/praviar ${"sk" + "_live_" + "1234567890abcdef"}`}
      />,
    );

    const alert = screen.getByRole("alert", {
      name: "Workspace temporarily unavailable",
    });

    expect(alert).toHaveAttribute("aria-atomic", "true");
    expect(screen.queryByText(/Reference:/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/postgres:\/\/secret-host/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/sk_live_1234567890abcdef/i),
    ).not.toBeInTheDocument();
  });

  it("normalizes prefixed support references", () => {
    render(
      <AppErrorState
        title="Workspace temporarily unavailable"
        description="Retry when the workspace connection is available."
        detail="Ref: digest-123"
      />,
    );

    expect(screen.getByText(/Reference:/)).toHaveTextContent(
      "Reference: digest-123",
    );
    expect(screen.queryByText(/Reference: Ref:/)).not.toBeInTheDocument();
  });

  it("uses unique labelled-by ids for repeated error titles", () => {
    render(
      <>
        <AppErrorState
          title="Workspace temporarily unavailable"
          description="Retry when the workspace connection is available."
        />
        <AppErrorState
          title="Workspace temporarily unavailable"
          description="Retry when the workspace connection is available."
        />
      </>,
    );

    const headings = screen.getAllByRole("heading", {
      name: "Workspace temporarily unavailable",
    });
    const headingIds = headings.map((heading) => heading.id);

    expect(headingIds.every(Boolean)).toBe(true);
    expect(new Set(headingIds).size).toBe(2);
  });
});
