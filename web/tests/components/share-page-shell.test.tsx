import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/app/share/[token]/shared-report-card", () => ({
  SharedReportCard: ({ report }: { report: { compound_name: string } }) => (
    <div>Unlocked packet for {report.compound_name}</div>
  ),
}));

vi.mock("@/app/share/[token]/share-verification-prompt", () => ({
  ShareVerificationPrompt: () => <div>Recipient verification required</div>,
}));

import { SharePageShell } from "@/app/share/[token]/share-page-shell";

describe("SharePageShell verification session", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-24T10:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("relocks an open packet when its attributed session expires", () => {
    render(
      <SharePageShell
        token={"T".repeat(43)}
        initialResult={{
          status: "ok",
          report: {
            compound_name: "Succinic acid",
            overall_risk: "high",
            blocking_patents_count: 2,
            total_patents_found: 42,
            executive_summary: "Two patent families need review.",
            key_findings: [],
            generated_at: "2026-07-24T09:00:00.000Z",
            share_expires_at: "2026-08-24T10:00:00.000Z",
            verified_recipient_email: "counsel@example.com",
            attributable_view_number: 3,
            verified_session_expires_at: "2026-07-24T10:00:05.000Z",
          },
        }}
      />,
    );

    expect(
      screen.getByText("Unlocked packet for Succinic acid"),
    ).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5_001);
    });

    expect(screen.getAllByText("Recipient verification required")).toHaveLength(
      2,
    );
    expect(
      screen.queryByText("Unlocked packet for Succinic acid"),
    ).not.toBeInTheDocument();
  });
});
