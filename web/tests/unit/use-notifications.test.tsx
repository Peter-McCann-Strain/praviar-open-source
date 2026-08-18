import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockApiClient = vi.hoisted(() => vi.fn());

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: false,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: mockApiClient,
}));

import {
  type Notification,
  useResolveNotificationAction,
} from "@/hooks/use-notifications";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

const NOTIFICATION: Notification = {
  id: "11111111-1111-4111-8111-111111111111",
  type: "analysis_complete",
  title: "Analysis complete",
  body: "Your analysis is ready.",
  read: false,
  data: { analysis_id: "analysis-1" },
  created_at: "2026-07-16T12:00:00.000Z",
};

describe("useResolveNotificationAction", () => {
  beforeEach(() => {
    mockApiClient.mockReset();
  });

  it("asks the server to resolve the current notification action", async () => {
    mockApiClient.mockResolvedValue({
      notification_id: NOTIFICATION.id,
      actionable: true,
      destination: "/analyses/analysis-1/report",
      marked_read: true,
    });
    const { result } = renderHook(() => useResolveNotificationAction("tok"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync(NOTIFICATION);
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      `/notifications/${NOTIFICATION.id}/resolve-action`,
      {
        method: "POST",
        token: "tok",
      },
    );
  });

  it("fails closed without an authenticated session", async () => {
    const { result } = renderHook(() => useResolveNotificationAction(null), {
      wrapper: createWrapper(),
    });

    await expect(
      act(async () => {
        await result.current.mutateAsync(NOTIFICATION);
      }),
    ).rejects.toThrow(
      "Authenticated notification action resolution requires a token.",
    );
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
