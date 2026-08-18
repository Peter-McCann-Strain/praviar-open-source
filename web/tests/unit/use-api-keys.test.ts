import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

import {
  useAPIKeys,
  useCreateAPIKey,
  useRevokeAPIKey,
} from "@/hooks/use-api-keys";

const TEST_API_KEY = `prv_live_${"A".repeat(43)}`;
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

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

describe("useAPIKeys", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches API key list", async () => {
    const mockData = {
      items: [
        {
          id: "k1",
          name: "Production Key",
          key_prefix: "sk_prod1",
          scopes: ["analyses:read", "reports:read"],
          expires_at: "2026-06-20T09:30:00.000Z",
          revoked: false,
          last_used_at: null,
          created_at: "2026-03-20",
        },
        {
          id: "k2",
          name: "Staging Key",
          key_prefix: "sk_stag1",
          scopes: ["reports:read"],
          expires_at: "2026-07-20T09:30:00.000Z",
          revoked: false,
          last_used_at: "2026-03-19",
          created_at: "2026-03-18",
        },
      ],
      total: 2,
    };
    mockApiClient.mockResolvedValueOnce(mockData);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAPIKeys(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockData);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/api-keys?page=1",
      expect.objectContaining({ token: "test-token" }),
    );
  });

  it("returns empty list when no keys exist", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAPIKeys(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toEqual([]);
    expect(result.current.data?.total).toBe(0);
  });

  it("reports error when API call fails", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Unauthorized"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAPIKeys(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Unauthorized");
  });

  it("uses queryKey ['api-keys']", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAPIKeys(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiClient).toHaveBeenCalledWith(
      "/api-keys?page=1",
      expect.anything(),
    );
  });
});

describe("useCreateAPIKey", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls API with POST method", async () => {
    const mockResponse = {
      id: "k1",
      name: "New Key",
      key_prefix: "prv_live",
      secret_key: TEST_API_KEY,
      scopes: ["analyses:read", "reports:read"],
      expires_at: "2026-06-20T09:30:00.000Z",
      created_at: "2026-03-20",
    };
    mockApiClient.mockResolvedValueOnce(mockResponse);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAPIKey(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        name: "New Key",
        scopes: ["analyses:read", "reports:read"],
        expires_at: "2026-06-20T09:30:00.000Z",
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/api-keys",
      expect.objectContaining({
        method: "POST",
        token: "test-token",
      }),
    );

    // Verify the body
    const callArgs = mockApiClient.mock.calls[0];
    const bodyStr = callArgs[1]?.body as string;
    const body = JSON.parse(bodyStr);
    expect(body.name).toBe("New Key");
    expect(body.scopes).toEqual(["analyses:read", "reports:read"]);
    expect(body.expires_at).toBe("2026-06-20T09:30:00.000Z");
  });

  it("returns the secret key in creation response", async () => {
    const mockResponse = {
      id: "k1",
      name: "New Key",
      key_prefix: "prv_live",
      secret_key: TEST_API_KEY,
      scopes: ["reports:read"],
      expires_at: "2026-06-20T09:30:00.000Z",
      created_at: "2026-03-20",
    };
    mockApiClient.mockResolvedValueOnce(mockResponse);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAPIKey(), { wrapper });

    let response: typeof mockResponse | undefined;
    await act(async () => {
      response = await result.current.mutateAsync({
        name: "New Key",
        scopes: ["reports:read"],
        expires_at: "2026-06-20T09:30:00.000Z",
      });
    });

    expect(response?.secret_key).toBe(TEST_API_KEY);
  });

  it("reports error on failure", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Forbidden"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAPIKey(), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({
          name: "Fail Key",
          scopes: ["reports:read"],
          expires_at: "2026-06-20T09:30:00.000Z",
        });
      }),
    ).rejects.toThrow("Forbidden");
  });
});

describe("useRevokeAPIKey", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls API with DELETE method", async () => {
    mockApiClient.mockResolvedValueOnce({ status: "revoked" });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRevokeAPIKey(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("k1");
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/api-keys/k1",
      expect.objectContaining({
        method: "DELETE",
        token: "test-token",
      }),
    );
  });

  it("reports error on failure", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Key not found"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRevokeAPIKey(), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync("nonexistent");
      }),
    ).rejects.toThrow("Key not found");
  });
});
