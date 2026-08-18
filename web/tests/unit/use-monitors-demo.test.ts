import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockApiClient = vi.hoisted(() => vi.fn());
const CANONICAL_MONITOR_ID = "monitor-ana_fictional_0042";

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => null,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: mockApiClient,
  isAuthBoundaryError: () => false,
}));

import {
  useCreateMonitor,
  useDeleteMonitor,
  useDismissAlert,
  useMonitorAlerts,
  useMonitorForAnalysis,
  useMonitors,
  useUpdateMonitor,
} from "@/hooks/use-monitors";

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

describe("monitor hooks in demo mode", () => {
  beforeEach(() => {
    mockApiClient.mockClear();
  });

  it("serves seeded monitor and alert data without calling the API", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        monitors: useMonitors(),
        alerts: useMonitorAlerts(CANONICAL_MONITOR_ID),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.monitors.isSuccess).toBe(true));
    await waitFor(() => expect(result.current.alerts.isSuccess).toBe(true));

    expect(result.current.monitors.data?.items[0]?.compound_name).toBe(
      "Example Molecule Alpha watch",
    );
    expect(result.current.alerts.data?.items).toHaveLength(2);
    expect(result.current.alerts.data?.items[0]?.summary).toBe(
      "Fictional Patent Register B returned a partial synthetic snapshot.",
    );
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("finds a report monitor directly in demo mode", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useMonitorForAnalysis("ana_demo_001"), {
      wrapper,
    });

    await waitFor(() => expect(result.current).toBeDefined());
    expect(result.current?.id).toBe(CANONICAL_MONITOR_ID);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("paginates demo monitor and alert data", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        createMonitor: useCreateMonitor(),
      }),
      { wrapper },
    );

    await act(async () => {
      for (let index = 0; index < 25; index += 1) {
        await result.current.createMonitor.mutateAsync({
          compound_name: `Demo paginated watch ${index}`,
          compound_smiles: `CCO${index}`,
          schedule: "weekly",
        });
      }
    });

    const monitorsPage = renderHook(() => useMonitors(2, undefined, 20), {
      wrapper,
    });
    await waitFor(() =>
      expect(monitorsPage.result.current.isSuccess).toBe(true),
    );

    expect(monitorsPage.result.current.data?.page).toBe(2);
    expect(monitorsPage.result.current.data?.per_page).toBe(20);
    expect(monitorsPage.result.current.data?.total).toBeGreaterThan(20);
    expect(monitorsPage.result.current.data?.items.length).toBeLessThanOrEqual(
      20,
    );
    expect(monitorsPage.result.current.data?.items.length).toBeGreaterThan(0);

    const alertsPage = renderHook(
      () => useMonitorAlerts(CANONICAL_MONITOR_ID, 2, 1),
      { wrapper },
    );
    await waitFor(() => expect(alertsPage.result.current.isSuccess).toBe(true));

    expect(alertsPage.result.current.data).toEqual(
      expect.objectContaining({
        total: 2,
        page: 2,
        per_page: 1,
      }),
    );
    expect(alertsPage.result.current.data?.items).toHaveLength(1);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("mutates demo monitors locally without calling the API", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        createMonitor: useCreateMonitor(),
        updateMonitor: useUpdateMonitor(),
        deleteMonitor: useDeleteMonitor(),
        monitors: useMonitors(),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.monitors.isSuccess).toBe(true));

    let monitorId = "";
    await act(async () => {
      const created = await result.current.createMonitor.mutateAsync({
        compound_name: "Demo ethanol watch",
        compound_smiles: "CCO",
        schedule: "daily",
      });
      monitorId = created.id;
    });
    await act(async () => {
      await result.current.updateMonitor.mutateAsync({
        monitorId,
        data: { is_active: false, compound_name: "Paused ethanol watch" },
      });
    });

    const updatedMonitors = renderHook(() => useMonitors(), { wrapper });
    await waitFor(() =>
      expect(updatedMonitors.result.current.data?.items).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            id: monitorId,
            compound_name: "Paused ethanol watch",
            is_active: false,
          }),
        ]),
      ),
    );

    await act(async () => {
      await result.current.deleteMonitor.mutateAsync(monitorId);
    });

    const afterDelete = renderHook(() => useMonitors(), { wrapper });
    await waitFor(() =>
      expect(afterDelete.result.current.data?.items).not.toEqual(
        expect.arrayContaining([expect.objectContaining({ id: monitorId })]),
      ),
    );
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("dismisses demo alerts locally without calling the API", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        dismissAlert: useDismissAlert(),
        alerts: useMonitorAlerts(CANONICAL_MONITOR_ID),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.alerts.isSuccess).toBe(true));
    const alertId = result.current.alerts.data?.items[0]?.id;
    expect(alertId).toBeTruthy();

    await act(async () => {
      await result.current.dismissAlert.mutateAsync({
        monitorId: CANONICAL_MONITOR_ID,
        alertId: alertId!,
      });
    });

    const updatedAlerts = renderHook(
      () => useMonitorAlerts(CANONICAL_MONITOR_ID),
      { wrapper },
    );
    await waitFor(() =>
      expect(updatedAlerts.result.current.data?.items[0]).toEqual(
        expect.objectContaining({ id: alertId, dismissed: true }),
      ),
    );
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
