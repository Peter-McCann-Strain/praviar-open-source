import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { WatchToggle } from "@/components/report/watch-toggle";

function ControlledWatchToggle({
  onToggle,
}: {
  onToggle: (enabled: boolean, schedule: string) => void;
}) {
  const [enabled, setEnabled] = useState(false);

  return (
    <WatchToggle
      analysisId="test-123"
      enabled={enabled}
      onToggle={(nextEnabled, schedule) => {
        onToggle(nextEnabled, schedule);
        setEnabled(nextEnabled);
      }}
    />
  );
}

describe("WatchToggle", () => {
  it("renders Watch button when not enabled", () => {
    render(<WatchToggle analysisId="test-123" />);
    expect(screen.getByText("Watch")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Watch" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Watch" })).not.toHaveClass(
      "sm:min-h-8",
    );
  });

  it("toggles to Watching on click", () => {
    const onToggle = vi.fn();
    render(<ControlledWatchToggle onToggle={onToggle} />);
    fireEvent.click(screen.getByText("Watch"));
    expect(onToggle).toHaveBeenCalledWith(true, "weekly");
    expect(screen.getByText("Watching")).toBeInTheDocument();
  });

  it("shows frequency selector when enabled", () => {
    render(<WatchToggle analysisId="test-123" enabled />);
    expect(screen.getByText("Watching")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Weekly")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Weekly")).toHaveClass("min-h-11");
    expect(screen.getByDisplayValue("Weekly")).not.toHaveClass("sm:min-h-8");
  });

  it("shows active indicator when enabled", () => {
    render(<WatchToggle analysisId="test-123" enabled />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("persists frequency changes while enabled", () => {
    const onToggle = vi.fn();
    render(
      <WatchToggle
        analysisId="test-123"
        enabled
        schedule="weekly"
        onToggle={onToggle}
      />,
    );

    fireEvent.change(screen.getByLabelText("Watch frequency"), {
      target: { value: "daily" },
    });

    expect(onToggle).toHaveBeenCalledWith(true, "daily");

    fireEvent.change(screen.getByLabelText("Watch frequency"), {
      target: { value: "monthly" },
    });

    expect(onToggle).toHaveBeenLastCalledWith(true, "monthly");
  });

  it("syncs the selector from the persisted schedule", () => {
    render(<WatchToggle analysisId="test-123" enabled schedule="daily" />);
    expect(screen.getByDisplayValue("Daily")).toBeInTheDocument();
  });

  it("preserves monthly schedules and omits unsupported cadences", () => {
    render(<WatchToggle analysisId="test-123" enabled schedule="monthly" />);

    expect(screen.getByDisplayValue("Monthly")).toBeInTheDocument();
    expect(screen.queryByText("Bi-weekly")).not.toBeInTheDocument();
  });

  it("locks both watch controls while a sibling mutation is unresolved", () => {
    render(
      <WatchToggle analysisId="test-123" enabled isPending schedule="weekly" />,
    );

    expect(screen.getByRole("button", { name: "Watching" })).toBeDisabled();
    expect(screen.getByLabelText("Watch frequency")).toBeDisabled();
  });
});
