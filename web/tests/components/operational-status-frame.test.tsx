import { render, screen } from "@testing-library/react";
import { AlertTriangle } from "lucide-react";
import { describe, expect, it } from "vitest";

import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";

function renderFrame({
  isPending = false,
  tone = "default",
}: {
  isPending?: boolean;
  tone?: "default" | "warning" | "error";
}) {
  render(
    <OperationalStatusFrame
      contextItems={["No data changed"]}
      dataTestId="operational-state"
      description="Current workspace state."
      eyebrow="Workspace status"
      icon={AlertTriangle}
      isPending={isPending}
      recoveryBody="Retry when ready."
      recoveryTitle="Recovery"
      title="Workspace unavailable"
      titleId="workspace-unavailable-title"
      tone={tone}
    />,
  );
}

describe("OperationalStatusFrame", () => {
  it.each(["default", "warning"] as const)(
    "announces a non-destructive %s state politely",
    (tone) => {
      renderFrame({ tone });

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    },
  );

  it("reserves assertive alerts for destructive or loss states", () => {
    renderFrame({ tone: "error" });

    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
  });

  it("keeps recovery guidance before supporting context on narrow screens", () => {
    renderFrame({ tone: "warning" });

    expect(screen.getByText("Recovery").closest(".order-first")).not.toBeNull();
    expect(
      screen.getByText("No data changed").closest(".order-last"),
    ).not.toBeNull();
  });
});
