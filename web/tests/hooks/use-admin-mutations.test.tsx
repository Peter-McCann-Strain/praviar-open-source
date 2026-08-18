import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { APIError } from "@/lib/api-client";

const mockApiClient = vi.hoisted(() => vi.fn());
const mockAddToast = vi.hoisted(() => vi.fn());

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: false,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  apiClient: mockApiClient,
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: (
    selector: (state: { addToast: typeof mockAddToast }) => unknown,
  ) => selector({ addToast: mockAddToast }),
}));

vi.mock("@/lib/error-logger", () => ({
  logError: vi.fn(),
}));

import {
  useAdminOperations,
  useInviteUser,
  useReconcileAdminOperation,
  useUpdateUserRole,
} from "@/hooks/use-admin";

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

describe("admin mutation reconciliation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(crypto, "randomUUID").mockReturnValue(
      "11111111-1111-4111-8111-111111111111",
    );
  });

  it("reconciles a role operation after the provider accepted but the client timed out", async () => {
    mockApiClient.mockRejectedValueOnce(
      new DOMException("timed out after fetch", "AbortError"),
    );
    const mutationHook = renderHook(() => useUpdateUserRole(), {
      wrapper: createWrapper(),
    });
    const request = { userId: "user-1", role: "attorney" };

    await act(async () => {
      await expect(
        mutationHook.result.current.mutateAsync(request),
      ).rejects.toThrow("timed out after fetch");
    });
    expect(mutationHook.result.current.operationNotice).toEqual(
      expect.objectContaining({ kind: "unconfirmed" }),
    );
    expect(mockApiClient).toHaveBeenCalledTimes(1);
    mutationHook.unmount();

    const openOperation = {
      operation_id: "operation-1",
      operation_type: "role_update",
      state: "role_call_started",
      outcome_confirmed: false,
      reconciliation_required: true,
      provider_resource_id: null,
      target_user_id: "user-1",
      target_email_normalized: null,
      requested_role: "attorney",
      updated_at: "2026-07-14T08:00:00Z",
    };
    mockApiClient
      .mockResolvedValueOnce({ items: [openOperation] })
      .mockResolvedValueOnce({
        ...openOperation,
        operation_id: "operation-1",
        state: "completed",
        outcome_confirmed: true,
        reconciliation_required: false,
      })
      .mockResolvedValueOnce({
        items: [
          {
            ...openOperation,
            state: "completed",
            outcome_confirmed: true,
            reconciliation_required: false,
          },
        ],
      });
    const recovery = renderHook(
      () => ({
        operations: useAdminOperations(),
        reconciliation: useReconcileAdminOperation(),
      }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => {
      expect(
        recovery.result.current.operations.data?.items[0]?.operation_id,
      ).toBe("operation-1");
    });
    await act(async () => {
      await recovery.result.current.reconciliation.mutateAsync({
        operationId: "operation-1",
      });
    });

    expect(mockApiClient).toHaveBeenCalledTimes(4);
    expect(mockApiClient.mock.calls[0][0]).toBe("/admin/users/user-1/role");
    expect(mockApiClient.mock.calls[1][0]).toBe("/admin/operations");
    expect(mockApiClient.mock.calls[2][0]).toBe(
      "/admin/operations/operation-1/reconcile",
    );
    expect(mockApiClient.mock.calls[3][0]).toBe("/admin/operations");
  });

  it("sends the explicit partial-role recovery action and no broader replay request", async () => {
    mockApiClient.mockResolvedValueOnce({
      operation_id: "operation-partial-1",
      operation_type: "role_update",
      state: "completed",
      outcome_confirmed: true,
      reconciliation_required: false,
      recovery_available: false,
      recovery_action: null,
      provider_resource_id: null,
      target_user_id: "user-1",
      target_email_normalized: null,
      requested_role: "client",
      updated_at: "2026-07-14T08:05:00Z",
    });
    const { result } = renderHook(() => useReconcileAdminOperation(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        operationId: "operation-partial-1",
        recoveryAction: "retry_rejected_role",
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/admin/operations/operation-partial-1/reconcile",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ recovery_action: "retry_rejected_role" }),
      }),
    );
  });

  it("uses a new invite key after a confirmed provider rejection", async () => {
    vi.mocked(crypto.randomUUID)
      .mockReturnValueOnce("11111111-1111-4111-8111-111111111111")
      .mockReturnValueOnce("22222222-2222-4222-8222-222222222222");
    mockApiClient
      .mockRejectedValueOnce(
        new APIError(502, "Clerk rejected the request (422)", {
          type: "https://problems.praviar.invalid/admin-operation-terminal-failure",
        }),
      )
      .mockResolvedValueOnce({ status: "invited" });
    const { result } = renderHook(() => useInviteUser(), {
      wrapper: createWrapper(),
    });
    const request = { email: "Buyer@Example.com", role: "client" };

    await act(async () => {
      await expect(result.current.mutateAsync(request)).rejects.toThrow(
        "Clerk rejected",
      );
    });
    expect(result.current.operationNotice).toEqual(
      expect.objectContaining({ kind: "failed", canReconcile: false }),
    );
    await act(async () => {
      await result.current.mutateAsync(request);
    });

    expect(mockApiClient).toHaveBeenCalledTimes(2);
    expect(mockApiClient.mock.calls[0][1].headers["Idempotency-Key"]).not.toBe(
      mockApiClient.mock.calls[1][1].headers["Idempotency-Key"],
    );
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.stringContaining("was rejected and was not applied"),
      "error",
    );
  });

  it.each([
    [403, "current access does not permit"],
    [422, "rejected before it could be applied"],
  ])(
    "treats a %s response as confirmed and does not retain its role key",
    async (status, expectedMessage) => {
      vi.mocked(crypto.randomUUID)
        .mockReturnValueOnce("11111111-1111-4111-8111-111111111111")
        .mockReturnValueOnce("22222222-2222-4222-8222-222222222222");
      mockApiClient
        .mockRejectedValueOnce(new APIError(status, "request rejected"))
        .mockResolvedValueOnce({ status: "updated" });
      const { result } = renderHook(() => useUpdateUserRole(), {
        wrapper: createWrapper(),
      });
      const request = { userId: "user-1", role: "attorney" };

      await act(async () => {
        await expect(result.current.mutateAsync(request)).rejects.toThrow(
          "request rejected",
        );
      });
      expect(result.current.operationNotice?.message).toContain(
        expectedMessage,
      );
      await act(async () => {
        await result.current.mutateAsync(request);
      });

      expect(
        mockApiClient.mock.calls[0][1].headers["Idempotency-Key"],
      ).not.toBe(mockApiClient.mock.calls[1][1].headers["Idempotency-Key"]);
      expect(
        mockApiClient.mock.calls.some(
          ([path]) =>
            String(path).includes("/admin/operations/") &&
            String(path).endsWith("/reconcile"),
        ),
      ).toBe(false);
    },
  );
});
