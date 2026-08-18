import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import * as React from "react";

import {
  useCreateReviewerDecision,
  useReviewerDecisions,
} from "@/hooks/use-reviewer-decisions";
import { authScopedQueryKey } from "@/lib/query-keys";
import { useToastStore } from "@/stores/toast-store";

const apiMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: (...args: unknown[]) => apiMock(...args),
}));

function createWrapperWithClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Provider = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Provider.displayName = "TestQueryProvider";
  return { client, wrapper: Provider };
}

function wrapper() {
  return createWrapperWithClient().wrapper;
}

describe("useReviewerDecisions", () => {
  beforeEach(() => {
    apiMock.mockReset();
    useToastStore.setState({ toasts: [] });
  });

  it("fetches decisions for an analysis via GET", async () => {
    apiMock.mockResolvedValueOnce({
      items: [],
      counts: { accept: 0, reject: 0, edit: 0 },
    });
    const { result } = renderHook(
      () => useReviewerDecisions("abc-123", "tok"),
      {
        wrapper: wrapper(),
      },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiMock).toHaveBeenCalledWith(
      "/analyses/abc-123/decisions",
      expect.objectContaining({ token: "tok" }),
    );
  });

  it("is disabled without a token", () => {
    const { result } = renderHook(() => useReviewerDecisions("abc-123", null), {
      wrapper: wrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(apiMock).not.toHaveBeenCalled();
  });
});

describe("useCreateReviewerDecision", () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  it("POSTs with the right payload shape, defaulting empty note/edited_text", async () => {
    apiMock.mockResolvedValueOnce({ id: "new-1", decision: "accept" });
    const { result } = renderHook(
      () => useCreateReviewerDecision("abc-123", "tok"),
      { wrapper: wrapper() },
    );
    await act(async () => {
      await result.current.mutateAsync({
        finding_type: "patent",
        finding_ref: "US-123",
        decision: "accept",
      });
    });
    const [path, opts] = apiMock.mock.calls[0];
    expect(path).toBe("/analyses/abc-123/decisions");
    expect(opts.method).toBe("POST");
    expect(opts.token).toBe("tok");
    expect(JSON.parse(opts.body)).toEqual({
      finding_type: "patent",
      finding_ref: "US-123",
      decision: "accept",
      note: "",
      edited_text: "",
    });
  });

  it("invalidates the token-scoped decisions query after create", async () => {
    const { client, wrapper: Provider } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    apiMock.mockResolvedValueOnce({ id: "new-1", decision: "accept" });
    const { result } = renderHook(
      () => useCreateReviewerDecision("abc-123", "tok"),
      { wrapper: Provider },
    );

    await act(async () => {
      await result.current.mutateAsync({
        finding_type: "claim_element",
        finding_ref: "assertion-1",
        decision: "accept",
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["reviewer-decisions", "abc-123"],
        predicate: expect.any(Function),
      }),
    );
    const [{ predicate }] = invalidateSpy.mock.calls[0] as [
      { predicate: (query: { queryKey: readonly unknown[] }) => boolean },
    ];
    expect(
      predicate({
        queryKey: authScopedQueryKey(["reviewer-decisions", "abc-123"], "tok"),
      }),
    ).toBe(true);
    expect(
      predicate({
        queryKey: authScopedQueryKey(
          ["reviewer-decisions", "abc-123"],
          "other-token",
        ),
      }),
    ).toBe(false);
  });

  it("does not duplicate inline save recovery with a global error toast", async () => {
    apiMock.mockRejectedValueOnce(
      new Error("postgres://secret-token reviewer backend exploded"),
    );
    const { result } = renderHook(
      () => useCreateReviewerDecision("abc-123", "tok"),
      { wrapper: wrapper() },
    );

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          finding_type: "patent",
          finding_ref: "US-123",
          decision: "reject",
        }),
      ).rejects.toThrow("postgres://secret-token reviewer backend exploded");
    });

    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(0);
  });
});
