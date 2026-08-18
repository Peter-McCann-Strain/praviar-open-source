import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useClaimedUseReceipts,
  useIssueClaimedUseReceipt,
  useRevokeClaimedUseReceipt,
} from "@/hooks/use-claimed-use-receipts";
import {
  buildClaimedUseReceipt,
  buildClaimedUseReceiptLedger,
  buildRevokedClaimedUseReceipt,
} from "../fixtures/claimed-use-receipts";

const apiMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: (...args: unknown[]) => apiMock(...args),
}));

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function TestQueryProvider({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("claimed-use receipt hooks", () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  it("loads the org-scoped receipt ledger with the bearer token", async () => {
    apiMock.mockResolvedValueOnce(buildClaimedUseReceiptLedger());
    const { result } = renderHook(
      () => useClaimedUseReceipts("analysis-1", "token-1"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiMock).toHaveBeenCalledWith(
      "/analyses/analysis-1/claimed-use-receipts",
      expect.objectContaining({ token: "token-1" }),
    );
  });

  it("issues only the exact current-report coordinates", async () => {
    apiMock.mockResolvedValueOnce(buildClaimedUseReceipt());
    const { result } = renderHook(
      () => useIssueClaimedUseReceipt("analysis-1", "token-1"),
      { wrapper: wrapper() },
    );
    const input = {
      expected_report_id: "report-1",
      expected_report_fingerprint: "a".repeat(64),
      patent_id: "US12345678A1",
      claim_number: 1,
      accused_act_index: 0,
      claimed_use_match: true as const,
      product_identity_match: true as const,
    };

    await act(async () => {
      await result.current.mutateAsync(input);
    });

    expect(apiMock).toHaveBeenCalledWith(
      "/analyses/analysis-1/claimed-use-receipts",
      expect.objectContaining({
        method: "POST",
        token: "token-1",
        body: JSON.stringify(input),
      }),
    );
  });

  it("rejects legacy receipt payloads instead of rendering contract drift", async () => {
    const legacy = buildClaimedUseReceiptLedger();
    legacy.items[0].receipt = {
      ...legacy.items[0].receipt,
      schema_version: "claimed-use-match-v2",
    } as never;
    apiMock.mockResolvedValueOnce(legacy);

    const { result } = renderHook(
      () => useClaimedUseReceipts("analysis-1", "token-1"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it("uses the append-only revoke action rather than DELETE", async () => {
    apiMock.mockResolvedValueOnce(buildRevokedClaimedUseReceipt());
    const { result } = renderHook(
      () => useRevokeClaimedUseReceipt("analysis-1", "token-1"),
      { wrapper: wrapper() },
    );

    await act(async () => {
      await result.current.mutateAsync({
        receiptId: "receipt-1",
        reason: "The proposed label changed after counsel review.",
      });
    });

    expect(apiMock).toHaveBeenCalledWith(
      "/analyses/analysis-1/claimed-use-receipts/receipt-1/revoke",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          reason: "The proposed label changed after counsel review.",
        }),
      }),
    );
  });
});
