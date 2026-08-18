import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CreditPackCheckoutReconciliation } from "@/components/billing/credit-pack-reconciliation";

const mockReconciliation = vi.hoisted(() => ({
  data: {
    status: "pending",
    session_id: "cs_test_pending123",
  } as
    | {
        status: "pending";
        session_id: string;
      }
    | {
        status: "applied";
        session_id: string;
        ledger_entry_id: string;
        credit_pack_id: "single_analysis" | "portfolio_5";
        credits_applied: number;
        current_purchased_credits_balance: number;
        applied_at: string;
      },
  error: null as unknown,
  isFetching: false,
  pollingTimedOut: false,
  refetch: vi.fn(),
}));

vi.mock("@/hooks/use-billing", () => ({
  useCreditPackCheckoutReconciliation: () => mockReconciliation,
  isStripeCheckoutSessionId: (value: string | null | undefined) =>
    Boolean(value && /^cs_(?:test|live)_[A-Za-z0-9]+$/u.test(value)),
}));

describe("CreditPackCheckoutReconciliation", () => {
  beforeEach(() => {
    mockReconciliation.data = {
      status: "pending",
      session_id: "cs_test_pending123",
    };
    mockReconciliation.error = null;
    mockReconciliation.isFetching = false;
    mockReconciliation.pollingTimedOut = false;
    mockReconciliation.refetch.mockReset();
  });

  it("fails closed when the checkout return lacks a valid session", () => {
    render(
      <CreditPackCheckoutReconciliation
        currentConfirmedBalance={2}
        sessionId={null}
        surface="billing"
        token="tok"
      />,
    );

    expect(
      screen.getByText("Checkout return cannot be verified"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/No Report Credits are shown as applied/i),
    ).toBeInTheDocument();
  });

  it("shows pending without trusting the URL pack and supports manual checks", () => {
    render(
      <CreditPackCheckoutReconciliation
        currentConfirmedBalance={2}
        draftRestored
        sessionId="cs_test_pending123"
        surface="analysis"
        token="tok"
      />,
    );

    expect(
      screen.getByText("Checkout returned; Report Credits pending"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/return URL alone does not verify payment/i),
    ).toBeInTheDocument();
    expect(screen.getByText("2 Report Credits")).toBeInTheDocument();
    expect(
      screen.getByText(/reviewed launch packet remains restored/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Launch packet was not restored"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    expect(mockReconciliation.refetch).toHaveBeenCalledOnce();
  });

  it("warns analysis buyers when checkout returns but the launch draft is missing", () => {
    render(
      <CreditPackCheckoutReconciliation
        currentConfirmedBalance={2}
        draftRestored={false}
        sessionId="cs_test_pending123"
        surface="analysis"
        token="tok"
      />,
    );

    expect(
      screen.getByText("Checkout returned; Report Credits pending"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Launch packet was not restored"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Rebuild the launch packet before starting analysis/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no run has been submitted from the missing draft/i),
    ).toBeInTheDocument();
  });

  it("renders only authoritative applied pack, balance, audit, and receipt data", () => {
    mockReconciliation.data = {
      status: "applied",
      session_id: "cs_test_applied123",
      ledger_entry_id: "11111111-1111-4111-8111-111111111111",
      credit_pack_id: "portfolio_5",
      credits_applied: 5,
      current_purchased_credits_balance: 7,
      applied_at: "2026-07-16T08:00:00.000Z",
    };

    render(
      <CreditPackCheckoutReconciliation
        currentConfirmedBalance={2}
        sessionId="cs_test_applied123"
        surface="billing"
        token="tok"
      />,
    );

    expect(screen.getByText("5 Report Credits applied")).toBeInTheDocument();
    expect(
      screen.getByText(/Portfolio Pack · 5 Report Credits/i),
    ).toBeInTheDocument();
    expect(screen.getByText("7 Report Credits")).toBeInTheDocument();
    expect(
      screen.getByText(/Ledger 11111111-1111-4111-8111-111111111111/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Stripe payment confirmation recorded"),
    ).toBeInTheDocument();
  });

  it("keeps applied credits separate from a missing analysis launch draft", () => {
    mockReconciliation.data = {
      status: "applied",
      session_id: "cs_test_applied123",
      ledger_entry_id: "11111111-1111-4111-8111-111111111111",
      credit_pack_id: "single_analysis",
      credits_applied: 1,
      current_purchased_credits_balance: 3,
      applied_at: "2026-07-16T08:00:00.000Z",
    };

    render(
      <CreditPackCheckoutReconciliation
        currentConfirmedBalance={3}
        draftRestored={false}
        sessionId="cs_test_applied123"
        surface="analysis"
        token="tok"
      />,
    );

    expect(screen.getByText("1 Report Credit applied")).toBeInTheDocument();
    expect(
      screen.getByText("Launch packet was not restored"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/reviewed launch packet remains restored/i),
    ).not.toBeInTheDocument();
  });

  it("offers a durable launch-capacity retry after ledger application", () => {
    const onRefreshCapacity = vi.fn();
    mockReconciliation.data = {
      status: "applied",
      session_id: "cs_test_applied123",
      ledger_entry_id: "11111111-1111-4111-8111-111111111111",
      credit_pack_id: "single_analysis",
      credits_applied: 1,
      current_purchased_credits_balance: 1,
      applied_at: "2026-07-16T08:00:00.000Z",
    };

    render(
      <CreditPackCheckoutReconciliation
        capacityRefreshError
        currentConfirmedBalance={0}
        onRefreshCapacity={onRefreshCapacity}
        sessionId="cs_test_applied123"
        surface="analysis"
        token="tok"
      />,
    );

    expect(
      screen.getByText("Ledger confirmed; launch capacity refresh failed."),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Retry launch capacity" }),
    );
    expect(onRefreshCapacity).toHaveBeenCalledOnce();
  });

  it("keeps transport failures separate from purchase state", () => {
    mockReconciliation.error = new Error("private backend detail");

    render(
      <CreditPackCheckoutReconciliation
        currentConfirmedBalance={2}
        sessionId="cs_test_error123"
        surface="billing"
        token="tok"
      />,
    );

    expect(
      screen.getByText("Reconciliation status unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/private backend detail/i),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry status check" }));
    expect(mockReconciliation.refetch).toHaveBeenCalledOnce();
  });
});
