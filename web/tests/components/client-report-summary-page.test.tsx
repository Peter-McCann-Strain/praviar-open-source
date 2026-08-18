import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ClientReportSummaryPage } from "@/components/report-page/client-report-summary-page";

const mockRefetch = vi.fn();
const mockReplace = vi.fn();
const mockUseReportSummary = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

vi.mock("@/hooks/use-report", () => ({
  useReportSummary: (...args: unknown[]) => mockUseReportSummary(...args),
}));

describe("ClientReportSummaryPage", () => {
  beforeEach(() => {
    mockRefetch.mockReset();
    mockReplace.mockReset();
    mockUseReportSummary.mockReset();
  });

  it("renders a truthful counsel-only state for risk-restricted roles", () => {
    mockUseReportSummary.mockReturnValue({
      data: {
        overall_risk: null,
        blocking_patents_count: null,
        total_patents_found: 42,
        executive_summary:
          "Risk ratings and clearance conclusions are restricted to attorney-role users.",
        risk_ratings_restricted: true,
      },
      error: null,
      isLoading: false,
      refetch: mockRefetch,
    });

    render(<ClientReportSummaryPage analysisId="ana-client" />);

    expect(
      screen.getByRole("status", {
        name: "",
      }),
    ).toHaveTextContent("Governed conclusions are protected");
    expect(screen.getAllByText("Counsel-only")).toHaveLength(2);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("canonicalizes authorized principals to the full report workspace", async () => {
    mockUseReportSummary.mockReturnValue({
      data: {
        overall_risk: "high",
        blocking_patents_count: 3,
        total_patents_found: 18,
        executive_summary: "Three blocking patents require counsel review.",
        risk_ratings_restricted: false,
      },
      error: null,
      isLoading: false,
      refetch: mockRefetch,
    });

    render(<ClientReportSummaryPage analysisId="ana-attorney" />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Opening the full report workspace",
    );
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/analyses/ana-attorney/report");
    });
  });

  it("fails closed and lets the user retry an unavailable summary", () => {
    mockUseReportSummary.mockReturnValue({
      data: undefined,
      error: new Error("unavailable"),
      isLoading: false,
      refetch: mockRefetch,
    });

    render(<ClientReportSummaryPage analysisId="ana-error" />);
    fireEvent.click(screen.getByRole("button", { name: "Retry summary" }));

    expect(screen.getByRole("heading")).toHaveTextContent(
      "Report summary unavailable",
    );
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });
});
