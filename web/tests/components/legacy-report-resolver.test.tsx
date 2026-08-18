import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navigation = vi.hoisted(() => ({
  replace: vi.fn(),
  searchParams: new URLSearchParams(),
}));
const mockUseAuthToken = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => navigation.searchParams,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: vi.fn() };
});

import { LegacyReportResolver } from "@/components/report/legacy-report-resolver";
import { APIError, apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

describe("LegacyReportResolver", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.searchParams = new URLSearchParams();
    mockUseAuthToken.mockReturnValue("test-token");
  });

  it("resolves an immutable report UUID and preserves the deep-link query", async () => {
    const reportId = "5011f7bd-abf4-409a-b78d-c1d67ee804aa";
    mockApiClient.mockResolvedValueOnce({
      analysis_id: "416b8625-882a-4d79-b845-d2a8b9e81acc",
      report_id: reportId,
      matched_by: "report_id",
    });
    navigation.searchParams = new URLSearchParams({
      tab: "patents",
      patent: "WO0000000004A1",
    });

    render(<LegacyReportResolver id={reportId} />);

    await waitFor(() => {
      expect(navigation.replace).toHaveBeenCalledWith(
        "/analyses/416b8625-882a-4d79-b845-d2a8b9e81acc/report?tab=patents&patent=WO0000000004A1",
      );
    });
    expect(mockApiClient).toHaveBeenCalledWith(
      `/reports/resolve/${reportId}`,
      expect.objectContaining({ token: "test-token" }),
    );
  });

  it("renders a terminal not-found state for an unknown report reference", async () => {
    mockApiClient.mockRejectedValueOnce(
      new APIError(404, "The requested resource was not found."),
    );

    render(<LegacyReportResolver id="missing-report" />);

    expect(
      await screen.findByRole("heading", { name: "Report link not found" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to analyses" }),
    ).toHaveAttribute("href", "/analyses");
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it("keeps deterministic rpt_ana legacy references local", async () => {
    render(<LegacyReportResolver id="rpt_ana_123" />);

    await waitFor(() => {
      expect(navigation.replace).toHaveBeenCalledWith(
        "/analyses/ana_123/report",
      );
    });
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
