import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({
  apiClient: vi.fn(),
  isAuthBoundaryError: (error: unknown) =>
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    ((error as { status?: unknown }).status === 401 ||
      (error as { status?: unknown }).status === 403),
}));
const authTokenState = vi.hoisted(() => ({
  token: "test-token" as string | null,
}));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => authTokenState.token,
}));

import {
  useMonitors,
  useCreateMonitor,
  useUpdateMonitor,
  useDeleteMonitor,
  useDismissAlert,
  useMonitorForAnalysis,
  useMonitorForAnalysisState,
  useMonitorAlerts,
  type MonitorAlertResponse,
  type MonitorResponse,
} from "@/hooks/use-monitors";
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

function makeMonitor(
  overrides: Partial<MonitorResponse> = {},
): MonitorResponse {
  return {
    id: "m1",
    compound_smiles: "CC(=O)Oc1ccccc1C(=O)O",
    compound_name: "Aspirin Monitor",
    source_analysis_id: null,
    source_report_id: "report-1",
    source_trust_mode: "monitor",
    schedule: "weekly",
    is_active: true,
    jurisdiction_bundle: "major_markets",
    target_jurisdictions: ["US", "EP"],
    strategy_version: "2026-04-monitor-v1",
    monitoring_strategy: {},
    watch_targets: [],
    last_run_at: null,
    last_full_refresh_at: null,
    last_run_mode: "pending",
    last_run_status: "pending",
    last_run_summary: "Awaiting first run.",
    last_patent_count: 0,
    conclusion_status: "unbound",
    stale_conclusions: [],
    stale_conclusion_count: 0,
    created_at: "2026-03-20T00:00:00.000Z",
    ...overrides,
  };
}

function makeAlert(
  overrides: Partial<MonitorAlertResponse> = {},
): MonitorAlertResponse {
  return {
    id: "a1",
    monitor_id: "m1",
    new_patent_ids: ["US12345"],
    new_patent_count: 1,
    run_at: "2026-03-20T00:00:00.000Z",
    dismissed: false,
    created_at: "2026-03-20T00:05:00.000Z",
    summary: "New patent event surfaced.",
    ...overrides,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
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

describe("useMonitors", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authTokenState.token = "test-token";
  });

  it("fetches monitor list", async () => {
    const mockData = {
      items: [makeMonitor()],
      total: 1,
    };
    mockApiClient.mockResolvedValueOnce(mockData);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitors(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({
      ...mockData,
      page: 1,
      per_page: 20,
    });
    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors?page=1&per_page=20",
      expect.objectContaining({ token: "test-token" }),
    );
  });

  it("passes page parameter", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitors(3), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors?page=3&per_page=20",
      expect.anything(),
    );
    expect(result.current.data).toEqual({
      items: [],
      total: 0,
      page: 3,
      per_page: 20,
    });
  });

  it("passes active and per-page parameters", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitors(2, false, 10), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors?page=2&per_page=10&is_active=false",
      expect.anything(),
    );
    expect(result.current.data).toEqual({
      items: [],
      total: 0,
      page: 2,
      per_page: 10,
      is_active: false,
    });
  });

  it("reports error when API call fails", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Network error"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitors(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Network error");
  });

  it("does not expose cached monitor rows after the token is removed", async () => {
    authTokenState.token = "token-a";
    const firstData = {
      items: [makeMonitor({ id: "m-org-a", compound_name: "Org A Monitor" })],
      total: 1,
    };
    mockApiClient.mockResolvedValueOnce(firstData);

    const wrapper = createWrapper();
    const { result, rerender } = renderHook(() => useMonitors(), { wrapper });

    await waitFor(() =>
      expect(result.current.data?.items[0]?.id).toBe("m-org-a"),
    );

    authTokenState.token = null;
    rerender();

    expect(result.current.data).toBeUndefined();
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).toHaveBeenCalledTimes(1);
  });

  it("does not reuse cached monitor rows across auth scopes", async () => {
    authTokenState.token = "token-a";
    const firstData = {
      items: [makeMonitor({ id: "m-org-a", compound_name: "Org A Monitor" })],
      total: 1,
    };
    const secondData = {
      items: [makeMonitor({ id: "m-org-b", compound_name: "Org B Monitor" })],
      total: 1,
    };
    let resolveSecond: (value: unknown) => void;
    const secondRequest = new Promise((resolve) => {
      resolveSecond = resolve;
    });
    mockApiClient
      .mockResolvedValueOnce(firstData)
      .mockReturnValueOnce(secondRequest as any);

    const wrapper = createWrapper();
    const { result, rerender } = renderHook(() => useMonitors(), { wrapper });

    await waitFor(() =>
      expect(result.current.data?.items[0]?.id).toBe("m-org-a"),
    );

    authTokenState.token = "token-b";
    rerender();

    await waitFor(() => expect(mockApiClient).toHaveBeenCalledTimes(2));
    expect(result.current.data).toBeUndefined();

    await act(async () => {
      resolveSecond!(secondData);
    });

    await waitFor(() =>
      expect(result.current.data?.items[0]?.id).toBe("m-org-b"),
    );
  });

  it("uses the authoritative analysis lookup instead of a bounded monitor page", async () => {
    const monitor = makeMonitor({
      id: "m-report",
      source_analysis_id: "analysis-101",
    });
    mockApiClient.mockResolvedValueOnce(monitor);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitorForAnalysis("analysis-101"), {
      wrapper,
    });

    await waitFor(() => expect(result.current?.id).toBe("m-report"));
    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors/by-analysis/analysis-101",
      expect.objectContaining({ token: "test-token" }),
    );
  });

  it("returns no monitor when the authoritative lookup returns null", async () => {
    mockApiClient.mockResolvedValueOnce(null);

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useMonitorForAnalysisState("analysis-without-monitor"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.monitor).toBeUndefined();
  });

  it("hides a report-linked monitor when direct lookup access is revoked", async () => {
    mockApiClient
      .mockResolvedValueOnce(
        makeMonitor({ id: "m-report", source_analysis_id: "analysis-1" }),
      )
      .mockRejectedValueOnce({ status: 403, message: "Forbidden" });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useMonitorForAnalysisState("analysis-1"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.monitor?.id).toBe("m-report"));

    await act(async () => {
      await result.current.refetch();
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.monitor).toBeUndefined();
  });

  it("preserves a report-linked monitor when a background refetch has a non-auth error", async () => {
    mockApiClient
      .mockResolvedValueOnce(
        makeMonitor({ id: "m-report", source_analysis_id: "analysis-1" }),
      )
      .mockRejectedValueOnce(new Error("Network error"));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useMonitorForAnalysisState("analysis-1"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.monitor?.id).toBe("m-report"));

    await act(async () => {
      await result.current.refetch();
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.monitor?.id).toBe("m-report");
  });
});

describe("useMonitorAlerts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authTokenState.token = "test-token";
  });

  it("fetches alerts for a monitor", async () => {
    const mockAlerts = {
      items: [makeAlert()],
      total: 1,
    };
    mockApiClient.mockResolvedValueOnce(mockAlerts);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitorAlerts("m1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({
      ...mockAlerts,
      page: 1,
      per_page: 20,
    });
    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors/m1/alerts?page=1&per_page=20",
      expect.objectContaining({ token: "test-token" }),
    );
  });

  it("passes alert page and per-page metadata", async () => {
    mockApiClient.mockResolvedValueOnce({
      items: [],
      total: 0,
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitorAlerts("m1", 3, 5), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors/m1/alerts?page=3&per_page=5",
      expect.objectContaining({ token: "test-token" }),
    );
    expect(result.current.data).toEqual({
      items: [],
      total: 0,
      page: 3,
      per_page: 5,
    });
  });

  it("is disabled when monitorId is empty", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitorAlerts(""), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("does not reuse cached alert rows across auth scopes", async () => {
    authTokenState.token = "token-a";
    const firstData = {
      items: [makeAlert({ id: "a-org-a", summary: "Org A alert" })],
      total: 1,
    };
    const secondData = {
      items: [makeAlert({ id: "a-org-b", summary: "Org B alert" })],
      total: 1,
    };
    let resolveSecond: (value: unknown) => void;
    const secondRequest = new Promise((resolve) => {
      resolveSecond = resolve;
    });
    mockApiClient
      .mockResolvedValueOnce(firstData)
      .mockReturnValueOnce(secondRequest as any);

    const wrapper = createWrapper();
    const { result, rerender } = renderHook(() => useMonitorAlerts("m1"), {
      wrapper,
    });

    await waitFor(() =>
      expect(result.current.data?.items[0]?.id).toBe("a-org-a"),
    );

    authTokenState.token = "token-b";
    rerender();

    await waitFor(() => expect(mockApiClient).toHaveBeenCalledTimes(2));
    expect(result.current.data).toBeUndefined();

    await act(async () => {
      resolveSecond!(secondData);
    });

    await waitFor(() =>
      expect(result.current.data?.items[0]?.id).toBe("a-org-b"),
    );
  });
});

describe("useCreateMonitor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authTokenState.token = "test-token";
  });

  it("calls API with POST method", async () => {
    const mockMonitor = {
      ...makeMonitor({
        id: "m1",
        compound_name: "New Monitor",
        compound_smiles: "CCO",
        schedule: "daily",
      }),
      schedule: "daily",
    };
    mockApiClient.mockResolvedValueOnce(mockMonitor);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateMonitor(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        compound_smiles: "CCO",
        compound_name: "Ethanol",
        schedule: "daily",
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors",
      expect.objectContaining({
        method: "POST",
        token: "test-token",
      }),
    );

    // Verify the body contains the correct data
    const callArgs = mockApiClient.mock.calls[0];
    const bodyStr = callArgs[1]?.body as string;
    const body = JSON.parse(bodyStr);
    expect(body.compound_smiles).toBe("CCO");
    expect(body.compound_name).toBe("Ethanol");
    expect(body.schedule).toBe("daily");
  });
});

describe("useUpdateMonitor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authTokenState.token = "test-token";
  });

  it("calls API with PATCH method", async () => {
    mockApiClient.mockResolvedValueOnce({});

    const wrapper = createWrapper();
    const { result } = renderHook(() => useUpdateMonitor(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        monitorId: "m1",
        data: { is_active: false },
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors/m1",
      expect.objectContaining({
        method: "PATCH",
        token: "test-token",
      }),
    );
  });
});

describe("useDeleteMonitor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authTokenState.token = "test-token";
  });

  it("calls API with DELETE method", async () => {
    mockApiClient.mockResolvedValueOnce({});

    const wrapper = createWrapper();
    const { result } = renderHook(() => useDeleteMonitor(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("m1");
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors/m1",
      expect.objectContaining({
        method: "DELETE",
        token: "test-token",
      }),
    );
  });

  it("reports error on failure", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Delete failed"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useDeleteMonitor(), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync("m1");
      }),
    ).rejects.toThrow("Delete failed");
  });
});

describe("useDismissAlert", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authTokenState.token = "test-token";
  });

  it("calls API with POST method", async () => {
    mockApiClient.mockResolvedValueOnce({ status: "dismissed" });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useDismissAlert(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ monitorId: "m1", alertId: "a1" });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/monitors/m1/alerts/a1/dismiss",
      expect.objectContaining({
        method: "POST",
        token: "test-token",
      }),
    );
  });

  it("reports error when dismiss fails", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Dismiss failed"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useDismissAlert(), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({ monitorId: "m1", alertId: "a1" });
      }),
    ).rejects.toThrow("Dismiss failed");
  });
});
