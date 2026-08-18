import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { APIError } from "@/lib/api-client";

const mockUseBatches = vi.hoisted(() => vi.fn());
const mockCancelMutateAsync = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-batch", () => ({
  useBatches: (...args: unknown[]) => mockUseBatches(...args),
  useCancelBatch: () => ({
    mutateAsync: mockCancelMutateAsync,
    isPending: false,
    isSuccess: false,
    variables: undefined,
  }),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "tok",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      role: "attorney",
      risk_ratings_restricted: false,
    },
  }),
}));

vi.mock("@/components/batch/create-batch-form", () => ({
  CreateBatchForm: () => <div data-testid="create-batch-form" />,
}));

vi.mock("@/components/batch/batch-detail-panel", () => ({
  BatchDetailPanel: () => <div data-testid="batch-detail-panel" />,
}));

vi.mock("@/components/batch/batch-summary-cards", () => ({
  BatchSummaryCards: () => <div data-testid="batch-summary-cards" />,
}));

vi.mock("@/components/batch/batches-table", () => ({
  BatchesTable: ({
    items,
    onCancel,
    cancelBlocked,
  }: {
    items: unknown[];
    onCancel: (batchId: string) => void;
    cancelBlocked?: boolean;
  }) => (
    <div data-testid="batches-table">
      {items.length} batch rows
      <button type="button" onClick={() => onCancel("batch-1")}>
        Cancel mocked batch
      </button>
      <span data-testid="batch-cancel-blocked">
        {cancelBlocked ? "blocked" : "ready"}
      </span>
    </div>
  ),
}));

vi.mock("@/components/batch/batch-pagination", () => ({
  BatchPagination: ({ total }: { total: number }) => (
    <div data-testid="batch-pagination">{total} total batches</div>
  ),
}));

import BatchPage from "@/app/(dashboard)/batch/page";

const batchList = {
  items: [
    {
      id: "batch-1",
      name: "Launch compounds",
      total_compounds: 3,
      completed_count: 2,
      failed_count: 0,
      status: "running",
      analysis_ids: [],
      created_at: "2026-06-01T10:00:00.000Z",
      updated_at: "2026-06-01T10:05:00.000Z",
    },
  ],
  total: 1,
};

describe("BatchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCancelMutateAsync.mockResolvedValue({
      id: "batch-1",
      cancelled: true,
    });
    mockUseBatches.mockReturnValue({
      data: batchList,
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn().mockResolvedValue({ data: batchList, error: null }),
    });
  });

  it("renders a governed loading state and disables creation", () => {
    mockUseBatches.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<BatchPage />);

    expect(
      screen.getByTestId("batch-workspace-status-loading"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Batch" })).toBeDisabled();
  });

  it("renders a safe retry state without exposing backend diagnostics", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseBatches.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("database host refused connection"),
      refetch,
    });

    render(
      <StrictMode>
        <BatchPage />
      </StrictMode>,
    );

    expect(
      screen.getByText("Diligence portfolio temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/database host refused/i),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Batch" })).toBeDisabled();
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(
      "[BatchPage]",
      "Batch workspace load failed",
      { action: "load" },
    );
    expect(JSON.stringify(consoleError.mock.calls)).not.toMatch(
      /database host refused/i,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Retry workspace load" }),
    );

    expect(refetch).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });

  it("shows access preparation when the batch query is disabled", () => {
    mockUseBatches.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<BatchPage />);

    expect(
      screen.getByText("Checking diligence portfolio workspace access"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Batch" })).toBeDisabled();
  });

  it("preserves stale batch data when a background refetch errors", () => {
    mockUseBatches.mockReturnValue({
      data: batchList,
      isLoading: false,
      error: new Error("background fetch failed"),
      refetch: vi.fn(),
    });

    render(<BatchPage />);

    expect(screen.getByTestId("batches-table")).toHaveTextContent(
      "1 batch rows",
    );
    expect(
      screen.queryByText("Diligence portfolio temporarily unavailable"),
    ).not.toBeInTheDocument();
  });

  it("hides cached batch data when access is revoked", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseBatches.mockReturnValue({
      data: batchList,
      isLoading: false,
      error: new APIError(401, "Authentication required"),
      refetch,
    });

    render(<BatchPage />);

    expect(
      screen.getByText("Diligence portfolio workspace access restricted"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("batches-table")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Portfolio control rail"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Batch" })).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry workspace load" }),
    );

    expect(refetch).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });

  it("keeps a rejected batch cancellation visible with an exact retry", async () => {
    mockCancelMutateAsync.mockRejectedValueOnce(
      new APIError(409, "Batch is already terminal"),
    );

    render(<BatchPage />);

    fireEvent.click(
      screen.getByRole("button", { name: "Cancel mocked batch" }),
    );

    expect(await screen.findByText("Batch was not cancelled")).toBeVisible();
    expect(screen.getByTestId("batch-cancel-recovery")).toHaveAttribute(
      "data-mutation-recovery-mode",
      "failed",
    );
    expect(screen.getByTestId("batch-cancel-blocked")).toHaveTextContent(
      "blocked",
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry cancellation" }));

    await waitFor(() => expect(mockCancelMutateAsync).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(
        screen.queryByTestId("batch-cancel-recovery"),
      ).not.toBeInTheDocument(),
    );
  });

  it("requires authoritative refresh after an ambiguous cancellation", async () => {
    const refetch = vi.fn().mockResolvedValue({ data: batchList, error: null });
    mockUseBatches.mockReturnValue({
      data: batchList,
      isLoading: false,
      isFetching: false,
      error: null,
      refetch,
    });
    mockCancelMutateAsync.mockRejectedValueOnce(
      new APIError(503, "Service unavailable"),
    );

    render(<BatchPage />);

    fireEvent.click(
      screen.getByRole("button", { name: "Cancel mocked batch" }),
    );

    expect(
      await screen.findByText("Batch cancellation outcome unconfirmed"),
    ).toBeVisible();
    expect(screen.getByTestId("batch-cancel-recovery")).toHaveAttribute(
      "data-mutation-recovery-mode",
      "outcome-unknown",
    );
    expect(
      screen.queryByRole("button", { name: "Keep batch active" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Refresh batch ledger" }),
    );

    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(
        screen.queryByTestId("batch-cancel-recovery"),
      ).not.toBeInTheDocument(),
    );
    expect(mockCancelMutateAsync).toHaveBeenCalledTimes(1);
  });
});
