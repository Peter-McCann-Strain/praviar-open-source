import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockApiClient = vi.hoisted(() => vi.fn());

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: mockApiClient,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => null,
}));

import {
  useAdminAuditLogs,
  useAdminHealth,
  useAdminMetrics,
  useAdminOrganizations,
  useAdminTasks,
  useAdminUsers,
} from "@/hooks/use-admin";

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

describe("admin hooks in demo mode", () => {
  beforeEach(() => {
    mockApiClient.mockReset();
  });

  it("serves every admin dashboard tab from local fixtures", async () => {
    const wrapper = createWrapper();
    const health = renderHook(() => useAdminHealth(), { wrapper });
    const organizations = renderHook(() => useAdminOrganizations(), {
      wrapper,
    });
    const users = renderHook(() => useAdminUsers(), { wrapper });
    const metrics = renderHook(() => useAdminMetrics(), { wrapper });
    const auditLogs = renderHook(() => useAdminAuditLogs(), { wrapper });
    const tasks = renderHook(() => useAdminTasks(), { wrapper });

    await waitFor(() => {
      expect(health.result.current.isSuccess).toBe(true);
      expect(organizations.result.current.isSuccess).toBe(true);
      expect(users.result.current.isSuccess).toBe(true);
      expect(metrics.result.current.isSuccess).toBe(true);
      expect(auditLogs.result.current.isSuccess).toBe(true);
      expect(tasks.result.current.isSuccess).toBe(true);
    });

    expect(health.result.current.data?.services[0]?.status).toBe("healthy");
    expect(organizations.result.current.data?.items[0]?.name).toBe(
      "Praviar Demo Biotech",
    );
    expect(users.result.current.data?.items[0]?.email).toBe("ada@example.com");
    expect(users.result.current.data?.items.map((user) => user.role)).toEqual([
      "admin",
      "attorney",
      "scientist",
    ]);
    expect(metrics.result.current.data?.total_analyses).toBeGreaterThan(0);
    expect(auditLogs.result.current.data?.items[0]?.action).toBe(
      "report.export.queued",
    );
    expect(tasks.result.current.data?.inspectable).toBe(true);
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
