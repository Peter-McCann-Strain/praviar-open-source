import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock api-client before importing hooks
vi.mock("@/lib/api-client", () => ({
  apiClient: vi.fn(),
}));

import {
  useAnalyses,
  useAnalysis,
  useCreateAnalysis,
} from "@/hooks/use-analysis";
import { apiClient } from "@/lib/api-client";
import { ANALYSIS_SEARCH_MAX_LENGTH } from "@/lib/analysis-search";

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

function createLaunchInput(overrides: Record<string, unknown> = {}) {
  return {
    client_idempotency_key: "analysis-launch-hook-test-123",
    compound_input: "aspirin",
    input_type: "name" as const,
    submitted_identity_confirmed: true as const,
    submitted_identity_value: "aspirin",
    ...overrides,
  };
}

describe("useAnalyses", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("is disabled when token is null", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalyses(null), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("is disabled when token is empty string", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalyses(""), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("fetches analyses when token is provided", async () => {
    const mockData = { items: [{ id: "a1", compound_name: "Test" }], total: 1 };
    mockApiClient.mockResolvedValueOnce(mockData);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalyses("test-token"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockData);
    expect(mockApiClient).toHaveBeenCalledWith(
      expect.stringContaining("/analyses"),
      expect.objectContaining({
        token: "test-token",
      }),
    );
  });

  it("uses queryKey ['analyses']", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalyses("tok"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Verify by checking the api was called (queryKey drives cache behavior)
    expect(mockApiClient).toHaveBeenCalledTimes(1);
  });

  it("clamps search before calling the analysis index API", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });
    const longSearch = ` ${"x".repeat(ANALYSIS_SEARCH_MAX_LENGTH + 24)} `;
    const expectedSearch = "x".repeat(ANALYSIS_SEARCH_MAX_LENGTH);
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useAnalyses("tok", 1, 20, "all", "all", longSearch),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiClient).toHaveBeenCalledWith(
      `/analyses?page=1&per_page=20&search=${expectedSearch}`,
      expect.objectContaining({
        token: "tok",
      }),
    );
  });

  it("strips risk filters and risk sorting at the query boundary for restricted roles", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });
    const wrapper = createWrapper();
    const { result } = renderHook(
      () =>
        useAnalyses(
          "tok",
          1,
          20,
          "completed",
          "high",
          "aspirin",
          "risk-desc",
          true,
        ),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses?page=1&per_page=20&status_filter=completed&search=aspirin",
      expect.objectContaining({ token: "tok" }),
    );
  });

  it("passes abort signal to apiClient", async () => {
    mockApiClient.mockResolvedValueOnce({ items: [], total: 0 });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalyses("tok"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiClient).toHaveBeenCalledWith(
      expect.stringContaining("/analyses"),
      expect.objectContaining({
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("transitions through loading states", async () => {
    let resolve: (v: unknown) => void;
    const pending = new Promise((r) => {
      resolve = r;
    });
    mockApiClient.mockReturnValueOnce(pending as any);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalyses("tok"), { wrapper });

    expect(result.current.isLoading).toBe(true);

    await act(async () => {
      resolve!({ items: [], total: 0 });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("does not expose a cached analysis list after the token is removed", async () => {
    const mockData = {
      items: [{ id: "a-private", compound_name: "Private Compound" }],
      total: 1,
    };
    mockApiClient.mockResolvedValueOnce(mockData);
    let token: string | null = "token-a";

    const wrapper = createWrapper();
    const { result, rerender } = renderHook(() => useAnalyses(token), {
      wrapper,
    });

    await waitFor(() => expect(result.current.data).toEqual(mockData));

    token = null;
    rerender();

    expect(result.current.data).toBeUndefined();
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).toHaveBeenCalledTimes(1);
  });

  it("does not reuse a cached analysis list across auth scopes", async () => {
    const firstData = {
      items: [{ id: "a-org-a", compound_name: "Org A Compound" }],
      total: 1,
    };
    const secondData = {
      items: [{ id: "a-org-b", compound_name: "Org B Compound" }],
      total: 1,
    };
    let resolveSecond: (value: unknown) => void;
    const secondRequest = new Promise((resolve) => {
      resolveSecond = resolve;
    });
    mockApiClient
      .mockResolvedValueOnce(firstData)
      .mockReturnValueOnce(secondRequest as any);
    let token = "token-a";

    const wrapper = createWrapper();
    const { result, rerender } = renderHook(() => useAnalyses(token), {
      wrapper,
    });

    await waitFor(() => expect(result.current.data).toEqual(firstData));

    token = "token-b";
    rerender();

    await waitFor(() => expect(mockApiClient).toHaveBeenCalledTimes(2));
    expect(result.current.data).toBeUndefined();

    await act(async () => {
      resolveSecond!(secondData);
    });

    await waitFor(() => expect(result.current.data).toEqual(secondData));
  });
});

describe("useAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("is disabled when token is null", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalysis("a1", null), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("is disabled when id is empty string", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalysis("", "tok"), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("fetches analysis by ID when both token and id are provided", async () => {
    const mockAnalysis = {
      id: "a1",
      compound_name: "Aspirin",
      status: "completed",
    };
    mockApiClient.mockResolvedValueOnce(mockAnalysis);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalysis("a1", "tok"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockAnalysis);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses/a1",
      expect.objectContaining({
        token: "tok",
      }),
    );
  });

  it("fetches with correct URL path containing the ID", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "abc", status: "completed" });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAnalysis("abc", "tok"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses/abc",
      expect.anything(),
    );
  });
});

describe("useCreateAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /analyses with correct data", async () => {
    const mockResult = {
      id: "new-1",
      compound_name: "Test",
      status: "pending",
    };
    mockApiClient.mockResolvedValueOnce(mockResult);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAnalysis("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(createLaunchInput());
    });

    expect(mockApiClient).toHaveBeenCalledWith("/analyses", {
      method: "POST",
      headers: { "Idempotency-Key": "analysis-launch-hook-test-123" },
      body: JSON.stringify({
        compound_input: "aspirin",
        input_type: "name",
        submitted_identity_confirmed: true,
        submitted_identity_value: "aspirin",
      }),
      token: "tok",
    });
  });

  it("passes config when provided", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "x" });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAnalysis("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(
        createLaunchInput({
          config: { max_analysis_patents: 10 },
        }),
      );
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses",
      expect.objectContaining({
        body: JSON.stringify({
          compound_input: "aspirin",
          input_type: "name",
          submitted_identity_confirmed: true,
          submitted_identity_value: "aspirin",
          config: { max_analysis_patents: 10 },
        }),
      }),
    );
  });

  it("passes launch trust and jurisdiction scope when provided", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "x" });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAnalysis("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(
        createLaunchInput({
          trust_mode: "counsel",
          jurisdiction_bundle: "europe_uk",
          target_jurisdictions: ["EP", "UK"],
          config: { max_analysis_patents: 10 },
        }),
      );
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses",
      expect.objectContaining({
        body: JSON.stringify({
          compound_input: "aspirin",
          input_type: "name",
          submitted_identity_confirmed: true,
          submitted_identity_value: "aspirin",
          trust_mode: "counsel",
          jurisdiction_bundle: "europe_uk",
          target_jurisdictions: ["EP", "UK"],
          config: { max_analysis_patents: 10 },
        }),
      }),
    );
  });

  it("passes matter scope preflight fields when provided", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "x" });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAnalysis("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(
        createLaunchInput({
          asset_type_hint: "markush_candidate",
          development_stage: "preclinical",
          intended_actions: ["design_around", "diligence_screen"],
        }),
      );
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses",
      expect.objectContaining({
        body: JSON.stringify({
          compound_input: "aspirin",
          input_type: "name",
          submitted_identity_confirmed: true,
          submitted_identity_value: "aspirin",
          asset_type_hint: "markush_candidate",
          development_stage: "preclinical",
          intended_actions: ["design_around", "diligence_screen"],
        }),
      }),
    );
  });

  it("calls apiClient with POST method and body", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "new" });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAnalysis("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(
        createLaunchInput({
          compound_input: "test",
          submitted_identity_value: "test",
        }),
      );
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          compound_input: "test",
          input_type: "name",
          submitted_identity_confirmed: true,
          submitted_identity_value: "test",
        }),
      }),
    );
  });

  it("sets isError on failure", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Server error"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAnalysis("tok"), { wrapper });

    // Use mutate (not mutateAsync) so rejection is handled internally
    act(() => {
      result.current.mutate(
        createLaunchInput({
          compound_input: "test",
          submitted_identity_value: "test",
        }),
      );
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it("uses undefined token when token is null", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "x" });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateAnalysis(null), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(
        createLaunchInput({
          compound_input: "test",
          submitted_identity_value: "test",
        }),
      );
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses",
      expect.objectContaining({
        token: undefined,
      }),
    );
  });
});
