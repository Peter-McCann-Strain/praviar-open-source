import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";

describe("AppSurfaceHeader", () => {
  it("keeps default consumers on the standard mobile rhythm", () => {
    render(
      <AppSurfaceHeader
        eyebrow="Workspace"
        title="Surface"
        description="Shared app chrome for product surfaces."
        metrics={[{ label: "State", value: "Ready" }]}
      />,
    );

    const header = screen.getByTestId("app-surface-header");

    expect(header).toHaveAttribute(
      "data-praviar-app-surface-density",
      "default",
    );
    expect(header).not.toHaveClass("py-4");
    expect(screen.getByLabelText("State: Ready")).toHaveClass("px-3");
  });

  it("uses a compact but narrow-phone-safe metric rhythm when requested", () => {
    render(
      <AppSurfaceHeader
        dataTestId="compact-app-surface-header"
        eyebrow="Control plane"
        title="Surface"
        description="Shared app chrome for utility surfaces."
        mobileDensity="compact"
        metrics={[
          { label: "Scope", value: "Organization" },
          { label: "Rotation", value: "90-day review" },
          { label: "Evidence", value: "Audit retained" },
        ]}
      />,
    );

    const header = screen.getByTestId("compact-app-surface-header");
    const metricGrid = screen.getByLabelText(
      "Scope: Organization",
    ).parentElement;

    expect(header).toHaveAttribute(
      "data-praviar-app-surface-density",
      "compact",
    );
    expect(header).toHaveClass("px-3", "py-4", "sm:px-6");
    expect(header.querySelector("[data-praviar-mark-frame]")).toHaveClass(
      "max-[359px]:hidden",
    );
    expect(metricGrid).toHaveClass("grid-cols-2", "min-[420px]:grid-cols-3");
    expect(screen.getByLabelText("Scope: Organization")).toHaveClass("px-2");
    expect(screen.getByTitle("Organization")).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
      "[word-break:normal]",
    );
  });

  it("allows secondary metrics to leave the narrow-phone headline set", () => {
    render(
      <AppSurfaceHeader
        eyebrow="Workspace"
        title="Surface"
        description="Primary signals remain visible."
        metrics={[
          { label: "Workspace", value: "250" },
          {
            label: "Updated",
            mobileHidden: true,
            value: "Just now",
          },
        ]}
      />,
    );

    expect(screen.getByLabelText("Workspace: 250")).not.toHaveClass("hidden");
    expect(screen.getByLabelText("Updated: Just now")).toHaveClass(
      "hidden",
      "sm:block",
    );
  });

  it("keeps three primary signals to two columns until values have safe mobile width", () => {
    render(
      <AppSurfaceHeader
        eyebrow="Workspace"
        title="Surface"
        description="Three primary signals stay balanced."
        mobileDensity="compact"
        mobileMetricColumns="three"
        metrics={[
          { label: "Workspace", value: "Focused coverage" },
          { label: "Live", value: "1 selected" },
          { label: "Review", value: "Expanded coverage" },
        ]}
      />,
    );

    expect(
      screen.getByLabelText("Workspace: Focused coverage").parentElement,
    ).toHaveClass("grid-cols-2", "min-[420px]:grid-cols-3");
    expect(screen.getByTitle("Focused coverage")).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });
});
