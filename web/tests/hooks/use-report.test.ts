import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({
  apiClient: vi.fn(),
}));

vi.mock("@/lib/constants", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/constants")>("@/lib/constants");

  return {
    ...actual,
    DEMO_MODE_ENABLED: true,
    DEV_AUTH_BYPASS_ENABLED: true,
  };
});

import { useReport, useReportSummary } from "@/hooks/use-report";
import { apiClient } from "@/lib/api-client";
import { createDemoAnalysis } from "@/lib/demo-data";

const mockApiClient = vi.mocked(apiClient);

const EMPTY_CLAIM_SOURCE_SPAN_MAP = {
  generated_from: "unit_test_fixture",
  entries: [],
  spans: {},
  unsupported_customer_visible_claim_count: 0,
  needs_review_count: 0,
};

const VALID_REPORT = {
  report_id: "r1",
  generated_at: "2026-03-10T12:00:00.000Z",
  compound: { name: "Aspirin", canonical_smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  risk_summary: { overall_risk: "medium", blocking_patents_count: 2 },
  patent_analyses: [],
  claim_source_span_map: EMPTY_CLAIM_SOURCE_SPAN_MAP,
};

const VALID_SUMMARY = {
  overall_risk: "high",
  blocking_patents_count: 5,
  total_patents_found: 100,
  executive_summary: "High risk detected.",
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

function jwt(claims: Record<string, unknown>) {
  const payload = btoa(JSON.stringify(claims))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `header.${payload}.signature`;
}

describe("useReport", () => {
  beforeEach(() => {
    mockApiClient.mockReset();
  });

  it("is disabled when token is null", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("a1", null), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves local demo reports in explicit demo mode without an API request", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("ana_demo_001", null), {
      wrapper,
    });

    expect(result.current.data?.report_id).toBe("rpt_ana_demo_001");
    expect(result.current.isLoading).toBe(false);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.report_id).toBe("rpt_ana_demo_001");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves local demo reports for legacy demo aliases", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("demo-analysis-001", null), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.report_id).toBe("rpt_ana_demo_001");
    expect(result.current.data?.compound.name).toBe("Example Molecule Alpha");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves reports for demo analyses created during the evaluator session", async () => {
    const analysis = createDemoAnalysis("celecoxib");
    const wrapper = createWrapper();

    const { result } = renderHook(() => useReport(analysis.id, "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.report_id).toBe(`rpt_${analysis.id}`);
    expect(result.current.data?.compound.name).toBe("Celecoxib");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("is disabled when analysisId is empty string", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("", "tok"), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("is disabled when both are empty", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("", ""), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches report by analysisId when both params are provided", async () => {
    mockApiClient.mockResolvedValueOnce(VALID_REPORT);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("a1", "tok"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(VALID_REPORT);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/a1",
      expect.objectContaining({
        token: "tok",
      }),
    );
  });

  it("has staleTime of Infinity", async () => {
    mockApiClient.mockResolvedValue(VALID_REPORT);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = function Wrapper({
      children,
    }: {
      children: React.ReactNode;
    }) {
      return React.createElement(
        QueryClientProvider,
        { client: queryClient },
        children,
      );
    };

    const { result } = renderHook(() => useReport("a1", "tok"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const firstCallCount = mockApiClient.mock.calls.length;

    // Re-render the hook — should NOT refetch because staleTime is Infinity
    const { result: result2 } = renderHook(() => useReport("a1", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result2.current.isSuccess).toBe(true));

    // The data should come from cache — no additional API call
    expect(mockApiClient.mock.calls.length).toBe(firstCallCount);
  });

  it("does not reuse cached reports across auth scopes", async () => {
    const firstReport = { ...VALID_REPORT, report_id: "tenant-a-report" };
    const secondReport = { ...VALID_REPORT, report_id: "tenant-b-report" };
    const firstToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:admin",
    });
    const secondToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:member",
    });
    mockApiClient
      .mockResolvedValueOnce(firstReport)
      .mockResolvedValueOnce(secondReport);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = function Wrapper({
      children,
    }: {
      children: React.ReactNode;
    }) {
      return React.createElement(
        QueryClientProvider,
        { client: queryClient },
        children,
      );
    };

    const { result: firstResult } = renderHook(
      () => useReport("a1", firstToken),
      {
        wrapper,
      },
    );
    await waitFor(() => expect(firstResult.current.isSuccess).toBe(true));

    const { result: secondResult } = renderHook(
      () => useReport("a1", secondToken),
      {
        wrapper,
      },
    );
    await waitFor(() => expect(secondResult.current.isSuccess).toBe(true));

    expect(firstResult.current.data).toEqual(firstReport);
    expect(secondResult.current.data).toEqual(secondReport);
    expect(mockApiClient).toHaveBeenCalledTimes(2);
  });

  it("uses the report endpoint for the analysis id", async () => {
    mockApiClient.mockResolvedValueOnce(VALID_REPORT);
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("analysis-xyz", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/analysis-xyz",
      expect.anything(),
    );
  });

  it("passes abort signal to apiClient", async () => {
    mockApiClient.mockResolvedValueOnce(VALID_REPORT);
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("a1", "tok"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/a1",
      expect.objectContaining({
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("reports error when API call fails", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Report not found"));
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReport("bad-id", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Report not found");
  });
});

describe("useReportSummary", () => {
  beforeEach(() => {
    mockApiClient.mockReset();
  });

  it("is disabled when token is null", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReportSummary("a1", null), {
      wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves local demo report summaries in explicit demo mode", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useReportSummary("ana_demo_001", null),
      {
        wrapper,
      },
    );

    expect(result.current.data).toMatchObject({
      overall_risk: "medium",
      blocking_patents_count: 0,
    });
    expect(result.current.isLoading).toBe(false);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      overall_risk: "medium",
      blocking_patents_count: 0,
    });
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves local demo summaries for legacy demo aliases", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useReportSummary("prv-demo-report", null),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      overall_risk: "medium",
      blocking_patents_count: 0,
    });
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves local summaries for generated demo analyses", async () => {
    const analysis = createDemoAnalysis("remdesivir");
    const wrapper = createWrapper();

    const { result } = renderHook(() => useReportSummary(analysis.id, "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.overall_risk).toBe("medium");
    expect(result.current.data?.executive_summary).toContain("Remdesivir");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("is disabled when analysisId is empty string", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReportSummary("", "tok"), {
      wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches report summary", async () => {
    mockApiClient.mockResolvedValueOnce(VALID_SUMMARY);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useReportSummary("a1", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(VALID_SUMMARY);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/a1/summary",
      expect.objectContaining({
        token: "tok",
      }),
    );
  });

  it("uses the report summary endpoint for the analysis id", async () => {
    mockApiClient.mockResolvedValueOnce({
      ...VALID_SUMMARY,
      overall_risk: "low",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReportSummary("a2", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // The endpoint reveals the queryKey structure
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/a2/summary",
      expect.anything(),
    );
  });

  it("does not have staleTime of Infinity (uses default caching)", async () => {
    // Verify it uses standard cache by making two renders with the same wrapper
    // and checking that refetch behavior is standard
    mockApiClient.mockResolvedValue({
      ...VALID_SUMMARY,
      overall_risk: "low",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReportSummary("a1", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Standard cache should return stale data, but the hook doesn't set staleTime: Infinity
    // This test verifies the hook doesn't explicitly prevent refetching like useReport does
    expect(result.current.isStale).toBe(true); // default staleTime is 0
  });

  it("reports error when API call fails", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Summary error"));
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReportSummary("bad", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Summary error");
  });

  it("passes abort signal to apiClient", async () => {
    mockApiClient.mockResolvedValueOnce({
      ...VALID_SUMMARY,
      overall_risk: "medium",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useReportSummary("a1", "tok"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/a1/summary",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });
});
