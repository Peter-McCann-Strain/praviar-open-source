import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
  DEV_AUTH_BYPASS_ENABLED: false,
}));

import { useReportSearch } from "@/hooks/use-report-search";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import { apiClient } from "@/lib/api-client";
import { REPORT_SEARCH_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";

const mockApiClient = vi.mocked(apiClient);

describe("useReportSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("initial state is empty", () => {
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBe("");
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("search sets isSearching to true", async () => {
    // Keep the promise pending so isSearching stays true
    let resolveSearch!: (v: unknown) => void;
    mockApiClient.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }) as any,
    );

    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    // Start a search but don't await completion
    act(() => {
      result.current.search("aspirin");
    });

    // Should immediately set query and isSearching
    expect(result.current.query).toBe("aspirin");
    expect(result.current.isSearching).toBe(true);

    // Clean up: resolve the pending promise
    await act(async () => {
      resolveSearch({
        query: "aspirin",
        interpreted_query: "aspirin compound",
        results: [],
        total: 0,
      });
    });
  });

  it("search clears on empty query", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin compound",
      results: [],
      total: 0,
    });

    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    // First do a search
    await act(async () => {
      await result.current.search("aspirin");
    });

    // Then clear by searching empty string
    await act(async () => {
      await result.current.search("");
    });

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBe("");
    expect(result.current.isShowingPreviousResults).toBe(false);
  });

  it("returns the authoritative response for exact-result routing", async () => {
    const response = {
      query: "WO2011123645",
      interpreted_query: 'Keyword search: "WO2011123645"',
      results: [
        {
          patent_id: "WO0000000004A1",
          section: "patent_analysis",
          relevance: 0.7,
          snippet: "Solid forms of an antiviral compound.",
        },
      ],
      total: 1,
    };
    mockApiClient.mockResolvedValueOnce(response);
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    let returned: unknown;
    await act(async () => {
      returned = await result.current.search("WO2011123645");
    });

    expect(returned).toEqual(response);
  });

  it("search clears on whitespace-only query", async () => {
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    await act(async () => {
      await result.current.search("   ");
    });

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
  });

  it("clears loading and error immediately when an in-flight query is emptied", async () => {
    let resolveSearch!: (v: unknown) => void;
    mockApiClient.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }) as any,
    );

    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    act(() => {
      result.current.search("aspirin");
    });

    expect(result.current.isSearching).toBe(true);

    await act(async () => {
      await result.current.search("");
    });

    expect(result.current.query).toBe("");
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);

    await act(async () => {
      resolveSearch({
        query: "aspirin",
        interpreted_query: "aspirin compound",
        results: [],
        total: 0,
      });
      await Promise.resolve();
    });

    expect(result.current.isSearching).toBe(false);
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
  });

  it("search completes and sets interpretedQuery", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin acetylsalicylic acid",
      results: [
        {
          patent_id: "US123",
          section: "claims",
          relevance: 0.95,
          snippet: "aspirin compound",
        },
      ],
      total: 12,
    });

    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    await act(async () => {
      await result.current.search("aspirin");
    });

    expect(result.current.isSearching).toBe(false);
    expect(result.current.interpretedQuery).toBe(
      "aspirin acetylsalicylic acid",
    );
    expect(result.current.resultQuery).toBe("aspirin");
    expect(result.current.failedQuery).toBe("");
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.results).toHaveLength(1);
    expect(result.current.totalResults).toBe(12);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/a1/search",
      expect.objectContaining({
        token: "test-token",
        method: "POST",
      }),
    );

    // Verify the body contains the query
    const callArgs = mockApiClient.mock.calls[0];
    const bodyStr = callArgs[1]?.body as string;
    const body = JSON.parse(bodyStr);
    expect(body.query).toBe("aspirin");
  });

  it("serves demo report searches locally without an API request or token", async () => {
    const { result } = renderHook(() => useReportSearch("ana_demo_001", null));

    await act(async () => {
      await result.current.search("blocking claim");
    });

    expect(mockApiClient).not.toHaveBeenCalled();
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.query).toBe("blocking claim");
    expect(result.current.resultQuery).toBe("blocking claim");
    expect(result.current.interpretedQuery).toContain(
      "materialized demo report",
    );
    expect(result.current.results.length).toBeGreaterThan(0);
    expect(result.current.results[0]?.snippet).toMatch(/claim/i);
    expect(result.current.totalResults).toBe(result.current.results.length);
  });

  it("clear resets all state", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin compound",
      results: [
        {
          patent_id: "US1",
          section: "claims",
          relevance: 0.9,
          snippet: "test",
        },
      ],
      total: 1,
    });

    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    // Do a search first
    await act(async () => {
      await result.current.search("aspirin");
    });

    // Clear
    act(() => {
      result.current.clear();
    });

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBe("");
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("clear works even when nothing was searched", () => {
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    act(() => {
      result.current.clear();
    });

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("exposes search and clear functions", () => {
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    expect(typeof result.current.search).toBe("function");
    expect(typeof result.current.clear).toBe("function");
  });

  it("error is initially null", () => {
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    expect(result.current.error).toBeNull();
  });

  it("sets safe error copy and preserves prior results when search fails", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin compound",
      results: [
        {
          patent_id: "US1",
          section: "claims",
          relevance: 0.9,
          snippet: "prior result",
        },
      ],
      total: 1,
    });

    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    await act(async () => {
      await result.current.search("aspirin");
    });

    mockApiClient.mockRejectedValueOnce(
      new Error("postgres://secret-token backend exploded"),
    );

    await act(async () => {
      await result.current.search("celecoxib");
    });

    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBe(REPORT_SEARCH_ERROR_MESSAGE);
    expect(result.current.error).not.toContain("postgres://secret-token");
    expect(result.current.resultQuery).toBe("aspirin");
    expect(result.current.failedQuery).toBe("celecoxib");
    expect(result.current.isShowingPreviousResults).toBe(true);
    expect(result.current.results).toEqual([
      {
        patent_id: "US1",
        section: "claims",
        relevance: 0.9,
        snippet: "prior result",
      },
    ]);
    expect(result.current.totalResults).toBe(1);
  });

  it("clears private search state on auth boundary changes", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin compound",
      results: [
        {
          patent_id: "US1",
          section: "claims",
          relevance: 0.9,
          snippet: "test",
        },
      ],
      total: 1,
    });
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    await act(async () => {
      await result.current.search("aspirin");
    });
    expect(result.current.results).toHaveLength(1);

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBe("");
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("does not repopulate private state when pre-boundary search resolves late", async () => {
    let resolveSearch!: (value: unknown) => void;
    mockApiClient.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }) as any,
    );
    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    act(() => {
      void result.current.search("aspirin");
    });
    expect(result.current.query).toBe("aspirin");

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    await act(async () => {
      resolveSearch({
        query: "aspirin",
        interpreted_query: "aspirin compound",
        results: [
          {
            patent_id: "US1",
            section: "claims",
            relevance: 0.9,
            snippet: "test",
          },
        ],
        total: 1,
      });
      await Promise.resolve();
    });

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.totalResults).toBe(0);
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBe("");
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
  });

  it("multiple searches update query each time", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "first",
      interpreted_query: "first compound",
      results: [],
      total: 0,
    });

    const { result } = renderHook(() => useReportSearch("a1", "test-token"));

    await act(async () => {
      await result.current.search("first");
    });

    expect(result.current.interpretedQuery).toBe("first compound");

    mockApiClient.mockResolvedValueOnce({
      query: "second",
      interpreted_query: "second compound",
      results: [],
      total: 0,
    });

    await act(async () => {
      await result.current.search("second");
    });

    expect(result.current.interpretedQuery).toBe("second compound");
  });
});
