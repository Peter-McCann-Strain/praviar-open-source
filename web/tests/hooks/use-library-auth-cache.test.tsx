import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({
  apiClient: vi.fn(),
}));

import { apiClient } from "@/lib/api-client";
import { useCompounds } from "@/hooks/use-compounds";
import { usePatents } from "@/hooks/use-patents";

const mockApiClient = vi.mocked(apiClient);

const patentRows = [
  {
    id: "p1",
    patent_number: "US0000000001A1",
    title: "Fermentation process",
    assignee: "Fictional Meridian Therapeutics",
    risk_level: "high",
    cpc_codes: ["C12P7/46"],
    expiry_date: "2038-01-15",
    analysis_id: "analysis-1",
    compound_name: "Succinic acid",
  },
];

const compoundRows = [
  {
    id: "c1",
    canonical_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    inchi_key: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    name: "Aspirin",
    molecular_formula: "C9H8O4",
    molecular_weight: 180.16,
    functional_groups: ["ester"],
    pubchem_cid: 2244,
    first_analyzed_at: "2026-03-20T12:00:00Z",
    analysis_count: 4,
  },
];

type PatentList = {
  items: typeof patentRows;
  total: number;
  page: number;
  per_page: number;
};

type CompoundList = {
  items: typeof compoundRows;
  total: number;
  page: number;
  per_page: number;
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
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

describe("private library hooks", () => {
  beforeEach(() => {
    mockApiClient.mockReset();
  });

  it("does not expose previous patent rows after the auth token is removed", async () => {
    mockApiClient.mockResolvedValueOnce({
      items: patentRows,
      total: 1,
      page: 1,
      per_page: 20,
    });
    const wrapper = createWrapper();
    const { result, rerender } = renderHook(
      ({ token }: { token: string | null }) => usePatents(token),
      { initialProps: { token: "token-1" }, wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0]?.patent_number).toBe("US0000000001A1");

    rerender({ token: null });

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
    expect(mockApiClient).toHaveBeenCalledTimes(1);
  });

  it("does not expose previous compound rows after the auth token is removed", async () => {
    mockApiClient.mockResolvedValueOnce({
      items: compoundRows,
      total: 1,
      page: 1,
      per_page: 20,
    });
    const wrapper = createWrapper();
    const { result, rerender } = renderHook(
      ({ token }: { token: string | null }) => useCompounds(token),
      { initialProps: { token: "token-1" }, wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0]?.name).toBe("Aspirin");

    rerender({ token: null });

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
    expect(mockApiClient).toHaveBeenCalledTimes(1);
  });

  it("does not expose previous patent rows when the auth token scope changes", async () => {
    let resolveSecondRequest: ((response: PatentList) => void) | undefined;
    mockApiClient
      .mockResolvedValueOnce({
        items: patentRows,
        total: 1,
        page: 1,
        per_page: 20,
      })
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveSecondRequest = resolve;
        }),
      );
    const wrapper = createWrapper();
    const { result, rerender } = renderHook(
      ({ token }: { token: string | null }) => usePatents(token),
      { initialProps: { token: "token-1" }, wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0]?.patent_number).toBe("US0000000001A1");

    rerender({ token: "token-2" });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(true);

    resolveSecondRequest?.({
      items: [{ ...patentRows[0], patent_number: "US20000000B2" }],
      total: 1,
      page: 1,
      per_page: 20,
    });

    await waitFor(() =>
      expect(result.current.data?.items[0]?.patent_number).toBe("US20000000B2"),
    );
  });

  it("does not expose previous compound rows when the auth token scope changes", async () => {
    let resolveSecondRequest: ((response: CompoundList) => void) | undefined;
    mockApiClient
      .mockResolvedValueOnce({
        items: compoundRows,
        total: 1,
        page: 1,
        per_page: 20,
      })
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveSecondRequest = resolve;
        }),
      );
    const wrapper = createWrapper();
    const { result, rerender } = renderHook(
      ({ token }: { token: string | null }) => useCompounds(token),
      { initialProps: { token: "token-1" }, wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0]?.name).toBe("Aspirin");

    rerender({ token: "token-2" });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(true);

    resolveSecondRequest?.({
      items: [{ ...compoundRows[0], name: "Ibuprofen" }],
      total: 1,
      page: 1,
      per_page: 20,
    });

    await waitFor(() =>
      expect(result.current.data?.items[0]?.name).toBe("Ibuprofen"),
    );
  });
});
