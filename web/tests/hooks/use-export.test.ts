import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/lib/constants", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/constants")>();
  return {
    ...actual,
    DEMO_MODE_ENABLED: false,
    EXPORT_POLL_INTERVAL_MS: 10,
  };
});

import { useExportReport, useExportStatus } from "@/hooks/use-export";
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useExportReport", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends POST with format and sections", async () => {
    mockApiClient.mockResolvedValueOnce({
      job_id: "j1",
      status: "pending",
      format: "pdf",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useExportReport("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        report_id: "r1",
        format: "pdf",
        sections: ["summary"],
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/r1/export",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ format: "pdf", sections: ["summary"] }),
      }),
    );
  });
});

describe("useExportStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is disabled when jobId is null", () => {
    const { result } = renderHook(() => useExportStatus(null, "tok"), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches export status when jobId provided", async () => {
    const data = {
      job_id: "j1",
      status: "completed",
      download_url: "/dl",
      format: "pdf",
      retryable: false,
    };
    mockApiClient.mockResolvedValueOnce(data);
    const { result } = renderHook(() => useExportStatus("j1", "tok"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);
  });

  it("keeps polling retryable failed exports", async () => {
    const data = {
      job_id: "j1",
      status: "processing",
      format: "pdf",
      retryable: true,
      retry_after_seconds: 5,
    };
    mockApiClient.mockResolvedValue(data);
    const { result } = renderHook(() => useExportStatus("j1", "tok"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() =>
      expect(mockApiClient.mock.calls.length).toBeGreaterThanOrEqual(2),
    );
  });
});
