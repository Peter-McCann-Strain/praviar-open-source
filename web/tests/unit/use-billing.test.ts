import { act, renderHook, waitFor } from "@testing-library/react";
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
  isStripeCheckoutSessionId,
  useCreditCapacityRequests,
  useCreateCheckout,
  useCreateCreditPackCheckout,
  useCreditPackCheckoutReconciliation,
  useCreatePortalSession,
  useRequestCreditCapacity,
  useResolveCreditCapacityRequest,
} from "@/hooks/use-billing";

function createWrapper(queryClient?: QueryClient) {
  const client =
    queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client }, children);
  };
}

describe("billing mutations", () => {
  beforeEach(() => {
    mockApiClient.mockReset();
  });

  it("fails closed before plan checkout when no auth token is available", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateCheckout(null), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({ plan_id: "pro" });
      }),
    ).rejects.toThrow("Authenticated plan checkout requires a token.");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("fails closed before credit checkout when no auth token is available", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateCreditPackCheckout(null), {
      wrapper,
    });

    await expect(
      act(async () => {
        await result.current.mutateAsync({ credit_pack_id: "portfolio_5" });
      }),
    ).rejects.toThrow("Authenticated credit checkout requires a token.");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("sends an authenticated in-app Report Credit request", async () => {
    mockApiClient.mockResolvedValue({
      notified_admins: 2,
      request_id: "11111111-1111-4111-8111-111111111111",
      requested_at: "2026-07-16T12:00:00.000Z",
      status: "sent",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useRequestCreditCapacity("tok"), {
      wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        requested_reports: 1,
        source: "analysis_launch",
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/billing/credit-capacity-requests",
      {
        method: "POST",
        body: JSON.stringify({
          requested_reports: 1,
          source: "analysis_launch",
        }),
        token: "tok",
      },
    );
  });

  it("loads durable Report Credit request history", async () => {
    mockApiClient.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      per_page: 20,
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreditCapacityRequests("tok"), {
      wrapper,
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/billing/credit-capacity-requests?page=1&per_page=20",
      expect.objectContaining({ token: "tok" }),
    );
  });

  it("paginates and filters durable Report Credit request history", async () => {
    mockApiClient.mockResolvedValue({
      items: [],
      total: 0,
      page: 3,
      per_page: 10,
    });
    const { result } = renderHook(
      () =>
        useCreditCapacityRequests("tok", {
          page: 3,
          perPage: 10,
          status: "fulfilled",
        }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/billing/credit-capacity-requests?page=3&per_page=10&status=fulfilled",
      expect.objectContaining({ token: "tok" }),
    );
  });

  it("resolves a pending Report Credit request with an administrator note", async () => {
    mockApiClient.mockResolvedValue({
      id: "11111111-1111-4111-8111-111111111111",
      status: "declined",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useResolveCreditCapacityRequest("tok"),
      { wrapper },
    );

    await act(async () => {
      await result.current.mutateAsync({
        requestId: "11111111-1111-4111-8111-111111111111",
        status: "declined",
        note: "  Use the next included allowance.  ",
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/billing/credit-capacity-requests/11111111-1111-4111-8111-111111111111/resolve",
      {
        method: "POST",
        body: JSON.stringify({
          status: "declined",
          note: "Use the next included allowance.",
        }),
        token: "tok",
      },
    );
  });

  it("fails closed before opening the billing portal without a token", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreatePortalSession(null), {
      wrapper,
    });

    await expect(
      act(async () => {
        await result.current.mutateAsync();
      }),
    ).rejects.toThrow("Authenticated billing portal access requires a token.");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("recognizes only real Stripe Checkout session identifier shapes", () => {
    expect(isStripeCheckoutSessionId("cs_test_abc123")).toBe(true);
    expect(isStripeCheckoutSessionId("cs_live_abc123")).toBe(true);
    expect(isStripeCheckoutSessionId("cs_demo_abc123")).toBe(false);
    expect(isStripeCheckoutSessionId("not-a-session")).toBe(false);
  });

  it("does not query reconciliation for an invalid session id", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useCreditPackCheckoutReconciliation("tok", "forged"),
      { wrapper },
    );

    expect(result.current.hasValidSessionId).toBe(false);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("refreshes request history and notifications after applied checkout", async () => {
    mockApiClient.mockResolvedValue({
      status: "applied",
      session_id: "cs_test_applied123",
      ledger_entry_id: "ledger-1",
      credit_pack_id: "portfolio_5",
      credits_applied: 5,
      current_purchased_credits_balance: 5,
      applied_at: "2026-07-16T12:00:00.000Z",
    });
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () => useCreditPackCheckoutReconciliation("tok", "cs_test_applied123"),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() => {
      expect(result.current.data?.status).toBe("applied");
      expect(invalidateSpy.mock.calls.length).toBeGreaterThanOrEqual(5);
    });
  });

  it("starts the reconciliation timeout only after the first pending response", async () => {
    vi.useFakeTimers();
    try {
      let resolveRequest:
        | ((value: { status: "pending"; session_id: string }) => void)
        | undefined;
      mockApiClient.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveRequest = resolve;
          }),
      );

      const { result } = renderHook(
        () => useCreditPackCheckoutReconciliation("tok", "cs_test_pending123"),
        { wrapper: createWrapper() },
      );

      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(result.current.pollingTimedOut).toBe(false);

      await act(async () => {
        resolveRequest?.({
          status: "pending",
          session_id: "cs_test_pending123",
        });
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current.data?.status).toBe("pending");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(59_000);
      });
      expect(result.current.pollingTimedOut).toBe(false);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });
      expect(result.current.pollingTimedOut).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("resets a timed-out session when the active reconciliation scope changes", async () => {
    vi.useFakeTimers();
    try {
      mockApiClient.mockImplementation((path: string) => {
        const sessionId = new URL(
          path,
          "https://praviar.local",
        ).searchParams.get("session_id");
        return Promise.resolve({
          status: "pending",
          session_id: sessionId,
        });
      });

      const { result, rerender } = renderHook(
        ({ sessionId }) =>
          useCreditPackCheckoutReconciliation("tok", sessionId),
        {
          initialProps: { sessionId: "cs_test_sessionA123" },
          wrapper: createWrapper(),
        },
      );

      await vi.waitFor(() =>
        expect(result.current.data?.session_id).toBe("cs_test_sessionA123"),
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(result.current.pollingTimedOut).toBe(true);

      rerender({ sessionId: "cs_test_sessionB123" });
      await vi.waitFor(() =>
        expect(result.current.data?.session_id).toBe("cs_test_sessionB123"),
      );
      expect(result.current.pollingTimedOut).toBe(false);

      rerender({ sessionId: "cs_test_sessionA123" });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current.pollingTimedOut).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("queries the exact session and invalidates dependent reads once applied", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");
    mockApiClient.mockResolvedValue({
      status: "applied",
      session_id: "cs_test_applied123",
      ledger_entry_id: "11111111-1111-4111-8111-111111111111",
      credit_pack_id: "portfolio_5",
      credits_applied: 5,
      current_purchased_credits_balance: 7,
      applied_at: "2026-07-16T08:00:00.000Z",
    });

    const { result } = renderHook(
      () => useCreditPackCheckoutReconciliation("tok", "cs_test_applied123"),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.data?.status).toBe("applied"));
    expect(mockApiClient).toHaveBeenCalledWith(
      "/billing/credit-packs/reconciliation?session_id=cs_test_applied123",
      expect.objectContaining({ token: "tok" }),
    );
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledTimes(5));
  });
});
