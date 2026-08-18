import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  formatHydrationStableTimestamp,
  useHydrationSafeRelativeTime,
} from "@/hooks/use-hydration-safe-relative-time";

function clockRelativeTime(date: string): string {
  const elapsedMinutes = Math.floor(
    (Date.now() - new Date(date).getTime()) / 60_000,
  );
  return `${elapsedMinutes}m ago`;
}

function RelativeTimestamp({ date }: { date: string }) {
  const formatRelativeTime = useHydrationSafeRelativeTime(clockRelativeTime);
  return <span>{formatRelativeTime(date)}</span>;
}

describe("useHydrationSafeRelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-17T12:15:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("uses deterministic UTC copy during server rendering", () => {
    expect(
      renderToString(<RelativeTimestamp date="2026-07-17T12:00:00.000Z" />),
    ).toContain("Jul 17, 2026");
  });

  it("switches to clock-relative copy in the browser", () => {
    render(<RelativeTimestamp date="2026-07-17T12:00:00.000Z" />);
    expect(screen.getByText("15m ago")).toBeInTheDocument();
  });

  it("handles invalid timestamps without leaking an invalid date", () => {
    expect(formatHydrationStableTimestamp("not-a-date")).toBe("Unknown");
  });
});
