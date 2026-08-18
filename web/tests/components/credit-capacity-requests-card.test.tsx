import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CreditCapacityRequestItem } from "@/hooks/use-billing";
import { APIError } from "@/lib/api-client";

const mockUseCreditCapacityRequests = vi.fn();
const mockResolveMutateAsync = vi.fn();
const mockAddToast = vi.fn();
const mockHistoryRefetch = vi.fn();
const mockPendingRefetch = vi.fn();

vi.mock("@/hooks/use-billing", () => ({
  useCreditCapacityRequests: (...args: unknown[]) =>
    mockUseCreditCapacityRequests(...args),
  useResolveCreditCapacityRequest: () => ({
    mutateAsync: mockResolveMutateAsync,
    isPending: false,
  }),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: (
    selector: (state: { addToast: typeof mockAddToast }) => unknown,
  ) => selector({ addToast: mockAddToast }),
}));

import { CreditCapacityRequestsCard } from "@/components/billing/credit-capacity-requests-card";

const PENDING_REQUEST: CreditCapacityRequestItem = {
  id: "11111111-2222-4333-8444-555555555555",
  requester_user_id: "user-1",
  requester_name: "Rina Scientist",
  requested_reports: 5,
  source: "analysis_launch",
  status: "pending",
  notified_admins: 2,
  requested_at: "2026-07-16T12:00:00.000Z",
  resolved_at: null,
  resolved_by_user_id: null,
  resolution_note: null,
  fulfillment_credit_ledger_id: null,
};

describe("CreditCapacityRequestsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCreditCapacityRequests.mockImplementation(
      (
        _token: string,
        options?: {
          perPage?: number;
        },
      ) => ({
        data:
          options?.perPage === 1
            ? { items: [], total: 1, page: 1, per_page: 1 }
            : {
                items: [PENDING_REQUEST],
                total: 1,
                page: 1,
                per_page: 10,
              },
        error: null,
        isLoading: false,
        refetch:
          options?.perPage === 1 ? mockPendingRefetch : mockHistoryRefetch,
      }),
    );
    mockResolveMutateAsync.mockResolvedValue({
      ...PENDING_REQUEST,
      status: "fulfilled",
      resolved_at: "2026-07-16T12:05:00.000Z",
      resolution_outcome: "resolved",
    });
  });

  it("verifies shared capacity without promising a reservation", async () => {
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    expect(screen.getByText("Rina Scientist")).toBeInTheDocument();
    expect(screen.getByText("Ref 11111111")).toBeInTheDocument();

    const note = screen.getByLabelText(/Resolution note/i);
    expect(note.tagName).toBe("TEXTAREA");
    fireEvent.change(note, {
      target: { value: "Portfolio pack approved." },
    });
    expect(screen.getByText("24/1,000")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Verify capacity" }));
    expect(
      screen.getByRole("heading", {
        name: "Verify current capacity?",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not reserve credits; every launch rechecks/i),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Verify current capacity" }),
    );

    await waitFor(() => {
      expect(mockResolveMutateAsync).toHaveBeenCalledWith({
        requestId: PENDING_REQUEST.id,
        status: "fulfilled",
        note: "Portfolio pack approved.",
      });
    });
    expect(mockAddToast).toHaveBeenCalledWith(
      "Current shared capacity verified for request 11111111. The requester was notified that capacity is not reserved.",
      "success",
    );
  });

  it("shows requesters durable status without administrator-only controls", () => {
    render(<CreditCapacityRequestsCard token="tok" canResolve={false} />);

    expect(screen.getByText("5 Report Credits")).toBeInTheDocument();
    expect(screen.getByText("Ref 11111111")).toBeInTheDocument();
    expect(screen.queryByText("Rina Scientist")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Verify capacity" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Track the durable status and reference/i),
    ).toBeInTheDocument();
  });

  it("requires a reason and confirmation before declining", () => {
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    const declineButton = screen.getByRole("button", { name: "Decline" });
    expect(declineButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Resolution note/i), {
      target: { value: "Capacity is already allocated." },
    });
    expect(declineButton).toBeEnabled();
    fireEvent.click(declineButton);

    expect(
      screen.getByRole("heading", {
        name: "Decline Report Credit request?",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Confirm decline" }),
    ).toBeInTheDocument();
  });

  it("keeps resolution failures visible inside the confirmation dialog", async () => {
    mockResolveMutateAsync.mockRejectedValueOnce(new Error("conflict"));
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    fireEvent.click(screen.getByRole("button", { name: "Verify capacity" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Verify current capacity" }),
    );

    const message =
      "Request 11111111 was not changed. Refresh the request list and retry.";
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(
      screen.getByRole("heading", {
        name: "Verify current capacity?",
      }),
    ).toBeInTheDocument();
    expect(mockAddToast).toHaveBeenCalledWith(message, "error");
  });

  it("keeps insufficient-capacity guidance inside the verification dialog", async () => {
    mockResolveMutateAsync.mockRejectedValueOnce(
      new APIError(
        409,
        "The request conflicts with the current state.",
        undefined,
        {
          typeUri: "https://problems.praviar.invalid/insufficient-capacity",
        },
      ),
    );
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    fireEvent.click(screen.getByRole("button", { name: "Verify capacity" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Verify current capacity" }),
    );

    const message =
      "Current shared capacity no longer covers 5 Report Credits. Add capacity, or decline it and ask the requester to submit a smaller request.";
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(
      screen.getByRole("heading", { name: "Verify current capacity?" }),
    ).toBeInTheDocument();
    expect(mockAddToast).toHaveBeenCalledWith(message, "error");
  });

  it("does not claim duplicate notification on an idempotent resolution", async () => {
    mockResolveMutateAsync.mockResolvedValueOnce({
      ...PENDING_REQUEST,
      status: "fulfilled",
      resolved_at: "2026-07-16T12:05:00.000Z",
      resolution_outcome: "already_resolved",
    });
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    fireEvent.click(screen.getByRole("button", { name: "Verify capacity" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Verify current capacity" }),
    );

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        "Request 11111111 already had a positive resolution. History was refreshed; no duplicate notification was sent.",
        "info",
      );
    });
  });

  it("closes and refreshes both histories when another admin resolved first", async () => {
    mockResolveMutateAsync.mockRejectedValueOnce(
      new APIError(
        409,
        "The request conflicts with the current state.",
        undefined,
        {
          typeUri:
            "https://problems.praviar.invalid/capacity-request-already-resolved",
        },
      ),
    );
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    fireEvent.click(screen.getByRole("button", { name: "Verify capacity" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Verify current capacity" }),
    );

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        "Another administrator already resolved request 11111111. History is refreshing to show the authoritative decision.",
        "info",
      );
    });
    expect(
      screen.queryByRole("heading", { name: "Verify current capacity?" }),
    ).not.toBeInTheDocument();
    expect(mockHistoryRefetch).toHaveBeenCalledTimes(1);
    expect(mockPendingRefetch).toHaveBeenCalledTimes(1);
  });

  it("distinguishes purchased credits from point-in-time verification", () => {
    mockUseCreditCapacityRequests.mockReturnValue({
      data: {
        items: [
          {
            ...PENDING_REQUEST,
            id: "aaaaaaaa-2222-4333-8444-555555555555",
            status: "fulfilled",
            resolved_at: "2026-07-16T12:05:00.000Z",
            resolved_by_user_id: "admin-1",
          },
          {
            ...PENDING_REQUEST,
            id: "bbbbbbbb-2222-4333-8444-555555555555",
            status: "fulfilled",
            resolved_at: "2026-07-16T12:06:00.000Z",
            resolved_by_user_id: "admin-1",
            fulfillment_credit_ledger_id:
              "cccccccc-2222-4333-8444-555555555555",
          },
        ],
        total: 2,
        page: 1,
        per_page: 10,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<CreditCapacityRequestsCard token="tok" canResolve={false} />);

    expect(screen.getByText("Capacity verified")).toBeInTheDocument();
    expect(screen.getByText("Credits added")).toBeInTheDocument();
    expect(screen.getByText(/No credits are reserved/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Fulfilled automatically from a confirmed/i),
    ).toBeInTheDocument();
  });

  it("paginates durable request history instead of capping it silently", () => {
    mockUseCreditCapacityRequests.mockImplementation(
      (
        _token: string,
        options?: {
          page?: number;
          status?: string;
        },
      ) => ({
        data:
          options?.status === "pending"
            ? { items: [], total: 17, page: 1, per_page: 1 }
            : {
                items: [PENDING_REQUEST],
                total: 25,
                page: options?.page ?? 1,
                per_page: 10,
              },
        error: null,
        isLoading: false,
        refetch: vi.fn(),
      }),
    );

    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText(/Showing 1–10 of 25/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(mockUseCreditCapacityRequests).toHaveBeenCalledWith(
      "tok",
      expect.objectContaining({ page: 2, perPage: 10 }),
    );
  });

  it("clamps to the last valid page when filtered totals shrink", async () => {
    let total = 21;
    mockUseCreditCapacityRequests.mockImplementation(
      (
        _token: string,
        options?: {
          page?: number;
          status?: string;
        },
      ) => ({
        data:
          options?.status === "pending"
            ? { items: [], total, page: 1, per_page: 1 }
            : {
                items: [PENDING_REQUEST],
                total,
                page: options?.page ?? 1,
                per_page: 10,
              },
        error: null,
        isLoading: false,
        refetch: vi.fn(),
      }),
    );

    const { rerender } = render(
      <CreditCapacityRequestsCard token="tok" canResolve />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("3 / 3")).toBeInTheDocument();

    total = 20;
    rerender(<CreditCapacityRequestsCard token="tok" canResolve />);

    expect(screen.queryByText("3 / 2")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mockUseCreditCapacityRequests).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({ page: 2, perPage: 10 }),
      );
    });
    expect(screen.queryByText(/21–20 of 20/)).not.toBeInTheDocument();
  });

  it("renders an honest empty history state", () => {
    mockUseCreditCapacityRequests.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 20 },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<CreditCapacityRequestsCard token="tok" canResolve={false} />);

    expect(
      screen.getByText("No Report Credit requests yet"),
    ).toBeInTheDocument();
  });

  it("renders a filter-specific empty state when other request states exist", () => {
    mockUseCreditCapacityRequests.mockImplementation(
      (
        _token: string,
        options?: {
          perPage?: number;
          status?: string;
        },
      ) => ({
        data:
          options?.perPage === 1
            ? { items: [], total: 1, page: 1, per_page: 1 }
            : options?.status === "declined"
              ? { items: [], total: 0, page: 1, per_page: 10 }
              : {
                  items: [PENDING_REQUEST],
                  total: 1,
                  page: 1,
                  per_page: 10,
                },
        error: null,
        isLoading: false,
        refetch: vi.fn(),
      }),
    );
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    fireEvent.click(screen.getByRole("button", { name: "Declined" }));

    expect(screen.getByText("No declined requests")).toBeInTheDocument();
    expect(
      screen.getByText(/Choose All to review other request states/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No Report Credit requests yet"),
    ).not.toBeInTheDocument();
  });

  it("uses customer-facing positive-resolution language in summaries", () => {
    mockUseCreditCapacityRequests.mockImplementation(
      (
        _token: string,
        options?: {
          perPage?: number;
          status?: string;
        },
      ) => ({
        data:
          options?.perPage === 1
            ? { items: [], total: 0, page: 1, per_page: 1 }
            : options?.status === "fulfilled"
              ? {
                  items: [
                    {
                      ...PENDING_REQUEST,
                      status: "fulfilled",
                      resolved_at: "2026-07-16T12:05:00.000Z",
                      resolved_by_user_id: "admin-1",
                    },
                  ],
                  total: 1,
                  page: 1,
                  per_page: 10,
                }
              : {
                  items: [PENDING_REQUEST],
                  total: 1,
                  page: 1,
                  per_page: 10,
                },
        error: null,
        isLoading: false,
        refetch: vi.fn(),
      }),
    );
    render(<CreditCapacityRequestsCard token="tok" canResolve />);

    fireEvent.click(
      screen.getByRole("button", { name: "Positive resolution" }),
    );

    expect(
      screen.getByText(/Showing 1–1 of 1 positive resolution request/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/fulfilled requests/i)).not.toBeInTheDocument();
  });
});
