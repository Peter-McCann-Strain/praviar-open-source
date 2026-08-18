import { describe, expect, it, beforeEach, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

const mockUseBillingStatus = vi.fn();
const mockUseUsageSummary = vi.fn();
const mockUseInvoices = vi.fn();
const mockUseCreateCheckout = vi.fn();
const mockUseCreateCreditPackCheckout = vi.fn();
const mockUseCreditPackCheckoutReconciliation = vi.fn();
const mockUseCreditCapacityRequests = vi.fn();
const mockUseResolveCreditCapacityRequest = vi.fn();
const mockUseCreatePortalSession = vi.fn();
const mockUseAuthToken = vi.fn();
const mockPrincipalState = vi.hoisted(() => ({
  canCreateAnalysis: true,
}));
const mockBillingAuth = vi.hoisted(() => ({
  hasClerk: false,
  isLoaded: true,
  orgRole: "org:admin" as string | null,
}));
const mockDemoRuntime = vi.hoisted(() => ({
  enabled: false,
}));
let mockSearchParams = new URLSearchParams();

vi.mock("@/lib/constants", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/constants")>();
  return {
    ...actual,
    get DEMO_MODE_ENABLED() {
      return mockDemoRuntime.enabled;
    },
  };
});

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: mockPrincipalState.canCreateAnalysis,
    },
  }),
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({
    isLoaded: mockBillingAuth.isLoaded,
    orgRole: mockBillingAuth.orgRole,
  }),
}));

vi.mock("@/components/layout/sidebar-constants", () => ({
  get hasClerk() {
    return mockBillingAuth.hasClerk;
  },
  isAdminOrgRole: (orgRole: string | null | undefined) =>
    orgRole === "org:admin" || orgRole === "admin",
}));

vi.mock("@/hooks/use-billing", () => ({
  useBillingStatus: () => mockUseBillingStatus(),
  useUsageSummary: () => mockUseUsageSummary(),
  useInvoices: () => mockUseInvoices(),
  useCreateCheckout: () => mockUseCreateCheckout(),
  useCreateCreditPackCheckout: () => mockUseCreateCreditPackCheckout(),
  useCreditPackCheckoutReconciliation: () =>
    mockUseCreditPackCheckoutReconciliation(),
  useCreditCapacityRequests: () => mockUseCreditCapacityRequests(),
  useResolveCreditCapacityRequest: () => mockUseResolveCreditCapacityRequest(),
  isStripeCheckoutSessionId: (value: string | null | undefined) =>
    Boolean(value && /^cs_(?:test|live)_[A-Za-z0-9]+$/u.test(value)),
  useCreatePortalSession: () => mockUseCreatePortalSession(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
}));

import BillingPage from "@/app/(dashboard)/billing/page";
import { isAllowedStripeRedirectUrl } from "@/components/billing/helpers";
import { useToastStore } from "@/stores/toast-store";

function forbiddenError() {
  return Object.assign(new Error("Forbidden"), { status: 403 });
}

function unauthorizedError() {
  return Object.assign(new Error("Unauthorized"), { status: 401 });
}

function mockStarterBillingAccount() {
  mockUseBillingStatus.mockReturnValue({
    data: {
      org_id: "org-1",
      plan: "starter",
      stripe_customer_id: "cus_123",
      stripe_subscription_id: "sub_123",
      subscription_status: "active",
      current_period_start: "2026-04-01T00:00:00.000Z",
      current_period_end: "2026-05-01T00:00:00.000Z",
      analyses_used: 21,
      analyses_limit: 31,
      included_analyses_limit: 25,
      purchased_credits_balance: 6,
      cancel_at_period_end: false,
    },
    error: null,
    isLoading: false,
    refetch: vi.fn(),
  });
  mockUseUsageSummary.mockReturnValue({
    data: {
      org_id: "org-1",
      plan: "starter",
      analyses_used: 21,
      analyses_limit: 31,
      included_analyses_limit: 25,
      purchased_credits_balance: 6,
      usage_pct: 67.7,
      cost_this_month_cents: 18400,
      overage_analyses: 0,
      period_start: "2026-04-01T00:00:00.000Z",
      period_end: "2026-05-01T00:00:00.000Z",
    },
    error: null,
    isLoading: false,
    refetch: vi.fn(),
  });
}

function expectBillingCreditReturnUrl(
  value: string,
  {
    checkout,
    creditPackId,
    pathname = "/billing",
  }: {
    checkout: "success" | "cancelled";
    creditPackId: string;
    pathname?: string;
  },
) {
  const url = new URL(value);

  expect(url.origin).toBe(window.location.origin);
  expect(url.pathname).toBe(pathname);
  expect(url.searchParams.get("checkout")).toBe(checkout);
  expect(url.searchParams.get("credit_pack")).toBe(creditPackId);
  expect(url.searchParams.get("intent")).toBe("credits");
}

describe("BillingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDemoRuntime.enabled = false;
    mockBillingAuth.hasClerk = false;
    mockBillingAuth.isLoaded = true;
    mockBillingAuth.orgRole = "org:admin";
    mockPrincipalState.canCreateAnalysis = true;
    mockSearchParams = new URLSearchParams();
    useToastStore.setState({ toasts: [] });
    mockUseAuthToken.mockReturnValue("tok");
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        stripe_customer_id: "cus_123",
        stripe_subscription_id: "sub_123",
        subscription_status: "active",
        current_period_start: "2026-04-01T00:00:00.000Z",
        current_period_end: "2026-05-01T00:00:00.000Z",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        usage_pct: 19.8,
        cost_this_month_cents: 18400,
        overage_analyses: 0,
        period_start: "2026-04-01T00:00:00.000Z",
        period_end: "2026-05-01T00:00:00.000Z",
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseInvoices.mockReturnValue({
      data: { invoices: [], has_more: false },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseCreateCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn(),
    });
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn(),
    });
    mockUseCreditPackCheckoutReconciliation.mockReturnValue({
      data: { status: "pending", session_id: "cs_test_pending123" },
      error: null,
      isFetching: false,
      pollingTimedOut: false,
      refetch: vi.fn(),
    });
    mockUseCreditCapacityRequests.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 20 },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseResolveCreditCapacityRequest.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn(),
    });
    mockUseCreatePortalSession.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn(),
    });
  });

  it("fails closed when billing status is forbidden", () => {
    mockUseBillingStatus.mockReturnValue({
      data: undefined,
      error: forbiddenError(),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getByText("Billing access restricted")).toBeInTheDocument();
    expect(
      screen.getByTestId("billing-account-control-restricted"),
    ).toHaveAttribute("data-praviar-status-frame", "true");
    expect(
      screen.getByRole("status", { name: "Billing access restricted" }),
    ).toHaveAttribute("aria-atomic", "true");
    expect(screen.queryByText("Subscription status")).not.toBeInTheDocument();
    expect(screen.queryByText("Current plan")).not.toBeInTheDocument();
    expect(screen.queryByText("Plan change controls")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Prepaid Report Credit capacity"),
    ).not.toBeInTheDocument();
  });

  it("fails closed when cached billing data is paired with an auth boundary error", () => {
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        stripe_customer_id: "cus_123",
        stripe_subscription_id: "sub_123",
        subscription_status: "active",
        current_period_start: "2026-04-01T00:00:00.000Z",
        current_period_end: "2026-05-01T00:00:00.000Z",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        cancel_at_period_end: false,
      },
      error: unauthorizedError(),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getByText("Billing access restricted")).toBeInTheDocument();
    expect(screen.queryByText("Subscription status")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Prepaid Report Credit capacity"),
    ).not.toBeInTheDocument();
  });

  it("does not default to a free plan when billing status fails", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseBillingStatus.mockReturnValue({
      data: undefined,
      error: new Error("Billing service unavailable"),
      isLoading: false,
      refetch,
    });

    render(<BillingPage />);

    expect(
      screen.getByText("Billing controls temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Detail:|Billing service unavailable/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Subscription status")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry control load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("keeps billing visible while invoice history has its own load failure", () => {
    const refetch = vi.fn();
    mockUseInvoices.mockReturnValue({
      data: undefined,
      error: new Error("invoice backend failed"),
      isLoading: false,
      refetch,
    });

    render(<BillingPage />);

    expect(screen.getByText("Subscription status")).toBeInTheDocument();
    const notice = screen.getByTestId("billing-invoice-status-notice");
    expect(notice).toHaveTextContent("Invoice history temporarily unavailable");
    expect(notice).toHaveTextContent(
      "Subscription, usage, and Report Credit balances remain visible",
    );
    fireEvent.click(
      within(notice).getByRole("button", { name: "Retry invoice history" }),
    );
    expect(refetch).toHaveBeenCalledOnce();
    expect(screen.queryByText("No invoices yet")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/invoice backend failed/i),
    ).not.toBeInTheDocument();
  });

  it("keeps billing controls visible when invoice history is forbidden", () => {
    mockUseInvoices.mockReturnValue({
      data: undefined,
      error: forbiddenError(),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getByText("Subscription status")).toBeInTheDocument();
    expect(
      screen.getByText("Prepaid Report Credit capacity"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("billing-invoice-status-notice"),
    ).toHaveTextContent("Invoice history access restricted");
    expect(
      screen.queryByText("Billing access restricted"),
    ).not.toBeInTheDocument();
  });

  it("hides cached invoice rows and governance affordances when invoice access is revoked", () => {
    mockUseInvoices.mockReturnValue({
      data: {
        has_more: false,
        invoices: [
          {
            id: "in_cached_123456",
            number: "SG-2026-0420",
            status: "paid",
            amount_due_cents: 49_900,
            amount_paid_cents: 49_900,
            currency: "usd",
            created_at: "2026-04-01T00:00:00.000Z",
            hosted_invoice_url: "https://invoice.stripe.com/i/in_cached",
            pdf_url: "https://pay.stripe.com/invoice/in_cached/pdf",
          },
        ],
      },
      error: forbiddenError(),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getByText("Subscription status")).toBeInTheDocument();
    expect(
      screen.getByTestId("billing-invoice-status-notice"),
    ).toHaveTextContent("Invoice history access restricted");
    expect(screen.queryByText("SG-2026-0420")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "View invoice SG-2026-0420" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Invoice links open hosted records in a new tab."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Invoice records appear here after the first successful payment.",
      ),
    ).toBeInTheDocument();
  });

  it("shows honest summary copy when no subscription is active", () => {
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        stripe_customer_id: null,
        stripe_subscription_id: null,
        subscription_status: null,
        current_period_start: null,
        current_period_end: null,
        analyses_used: 0,
        analyses_limit: 2,
        included_analyses_limit: 2,
        purchased_credits_balance: 0,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        analyses_used: 0,
        analyses_limit: 2,
        included_analyses_limit: 2,
        purchased_credits_balance: 0,
        usage_pct: 0,
        cost_this_month_cents: 0,
        overage_analyses: 0,
        period_start: null,
        period_end: null,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getAllByText("No subscription").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No renewal scheduled").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText("No subscription renewal is currently scheduled."),
    ).toBeInTheDocument();
  });

  it("announces successful Stripe checkout returns and refreshes billing data", async () => {
    const refetchBillingStatus = vi.fn();
    const refetchUsage = vi.fn();
    const refetchInvoices = vi.fn();
    mockSearchParams = new URLSearchParams("checkout=success");
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        stripe_customer_id: "cus_123",
        stripe_subscription_id: "sub_123",
        subscription_status: "active",
        current_period_start: "2026-04-01T00:00:00.000Z",
        current_period_end: "2026-05-01T00:00:00.000Z",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: refetchBillingStatus,
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        usage_pct: 19.8,
        cost_this_month_cents: 18400,
        overage_analyses: 0,
        period_start: "2026-04-01T00:00:00.000Z",
        period_end: "2026-05-01T00:00:00.000Z",
      },
      error: null,
      isLoading: false,
      refetch: refetchUsage,
    });
    mockUseInvoices.mockReturnValue({
      data: { invoices: [], has_more: false },
      error: null,
      isLoading: false,
      refetch: refetchInvoices,
    });

    render(<BillingPage />);

    expect(screen.getByText("Checkout returned")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Praviar is refreshing authoritative billing and Report Credit balances. This return alone does not confirm a change.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("status", { name: "Stripe reconciliation status" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Stripe reconciliation")).toBeInTheDocument();
    expect(
      screen.getByText("Refreshing balances and invoice records"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Current Report Credit balance"),
    ).toBeInTheDocument();
    expect(screen.getByText("Stripe-hosted checkout")).toBeInTheDocument();
    await waitFor(() => {
      expect(refetchBillingStatus).toHaveBeenCalledTimes(1);
      expect(refetchUsage).toHaveBeenCalledTimes(1);
      expect(refetchInvoices).toHaveBeenCalledTimes(1);
    });
  });

  it("waits for initial billing queries before reconciling a successful checkout", async () => {
    mockSearchParams = new URLSearchParams("checkout=success");
    const billingStatus = mockUseBillingStatus();
    const usage = mockUseUsageSummary();
    const invoices = mockUseInvoices();
    let initialQueriesLoading = true;
    mockUseBillingStatus.mockImplementation(() => ({
      ...billingStatus,
      isLoading: initialQueriesLoading,
    }));
    mockUseUsageSummary.mockImplementation(() => ({
      ...usage,
      isLoading: initialQueriesLoading,
    }));
    mockUseInvoices.mockImplementation(() => ({
      ...invoices,
      isLoading: initialQueriesLoading,
    }));

    const { rerender } = render(<BillingPage />);

    expect(billingStatus.refetch).not.toHaveBeenCalled();
    expect(usage.refetch).not.toHaveBeenCalled();
    expect(invoices.refetch).not.toHaveBeenCalled();

    initialQueriesLoading = false;
    rerender(<BillingPage />);

    await waitFor(() => {
      expect(billingStatus.refetch).toHaveBeenCalledTimes(1);
      expect(usage.refetch).toHaveBeenCalledTimes(1);
      expect(invoices.refetch).toHaveBeenCalledTimes(1);
    });
  });

  it("announces cancelled Stripe checkout returns without claiming a purchase", () => {
    mockSearchParams = new URLSearchParams("checkout=cancelled");

    render(<BillingPage />);

    expect(screen.getByText("Checkout flow cancelled")).toBeInTheDocument();
    expect(
      screen.getByText(
        "No billing or Report Credit changes are assumed from this browser return. Authoritative balances remain visible below.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Checkout returned")).not.toBeInTheDocument();
  });

  it("announces demo subscription portal returns without claiming a change", () => {
    mockDemoRuntime.enabled = true;
    mockSearchParams = new URLSearchParams("demo_portal=subscription");

    render(<BillingPage />);

    expect(screen.getByText("Subscription portal preview")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Demo portal navigation returned here. No subscription or credit changes were made.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Checkout complete")).not.toBeInTheDocument();
  });

  it("does not offer pay-as-you-go credits to enterprise accounts", () => {
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "enterprise",
        stripe_customer_id: "cus_123",
        stripe_subscription_id: "sub_123",
        subscription_status: "active",
        current_period_start: "2026-04-01T00:00:00.000Z",
        current_period_end: "2026-05-01T00:00:00.000Z",
        analyses_used: 21,
        analyses_limit: 0,
        included_analyses_limit: 0,
        purchased_credits_balance: 0,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "enterprise",
        analyses_used: 21,
        analyses_limit: 0,
        included_analyses_limit: 0,
        purchased_credits_balance: 0,
        usage_pct: 0,
        cost_this_month_cents: 0,
        overage_analyses: 0,
        period_start: "2026-04-01T00:00:00.000Z",
        period_end: "2026-05-01T00:00:00.000Z",
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.queryByText("Capacity runway")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Prepaid Report Credit capacity"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Review Report Credit Packs" }),
    ).not.toBeInTheDocument();
  });

  it("does not render free or upgrade UI while auth token is pending", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseBillingStatus.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.queryByText("Subscription status")).not.toBeInTheDocument();
    expect(screen.queryByText("Current plan")).not.toBeInTheDocument();
    expect(screen.queryByText("Plan change controls")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Prepaid Report Credit capacity"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Free")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Billing controls temporarily unavailable"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Checking billing controls access"),
    ).toBeInTheDocument();
  });

  it("announces the billing loading state", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseBillingStatus.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Loading billing controls")).toBeInTheDocument();
  });

  it("warns when cached billing status or usage may be stale", () => {
    const billingStatusRefetch = vi.fn();
    const usageRefetch = vi.fn();
    const invoiceRefetch = vi.fn();
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        stripe_customer_id: "cus_123",
        stripe_subscription_id: "sub_123",
        subscription_status: "active",
        current_period_start: "2026-04-01T00:00:00.000Z",
        current_period_end: "2026-05-01T00:00:00.000Z",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        cancel_at_period_end: false,
      },
      error: new Error("postgres timeout: billing_status"),
      isLoading: false,
      dataUpdatedAt: Date.parse("2026-07-16T07:00:00.000Z"),
      refetch: billingStatusRefetch,
    });
    mockUseUsageSummary.mockReturnValue({
      ...mockUseUsageSummary(),
      refetch: usageRefetch,
    });
    mockUseInvoices.mockReturnValue({
      ...mockUseInvoices(),
      refetch: invoiceRefetch,
    });

    render(<BillingPage />);

    expect(screen.getByText("Subscription status")).toBeInTheDocument();
    const staleNotice = screen.getByTestId("billing-stale-data-notice");
    expect(staleNotice).toHaveTextContent("Billing data may be stale");
    const billingHeading = screen.getByRole("heading", {
      name: "Credits & Billing",
    });
    const subscriptionHeading = screen.getByText("Subscription status");
    expect(
      billingHeading.compareDocumentPosition(staleNotice) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      staleNotice.compareDocumentPosition(subscriptionHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      within(staleNotice).getByText(
        /Billing refresh failed. Existing subscription and usage data is still shown/i,
      ),
    ).toBeInTheDocument();
    expect(staleNotice).toHaveTextContent(
      "Showing unchanged data from 16 Jul 2026, 07:00 UTC.",
    );
    fireEvent.click(
      within(staleNotice).getByRole("button", {
        name: "Retry billing data",
      }),
    );
    expect(billingStatusRefetch).toHaveBeenCalledOnce();
    expect(usageRefetch).toHaveBeenCalledOnce();
    expect(invoiceRefetch).toHaveBeenCalledOnce();
    expect(screen.queryByText(/postgres timeout/i)).not.toBeInTheDocument();
  });

  it("allows only Stripe-hosted billing redirects", () => {
    expect(
      isAllowedStripeRedirectUrl("https://checkout.stripe.com/c/pay"),
    ).toBe(true);
    expect(
      isAllowedStripeRedirectUrl("https://billing.stripe.com/p/session"),
    ).toBe(true);
    expect(isAllowedStripeRedirectUrl("https://evil.example/checkout")).toBe(
      false,
    );
    expect(isAllowedStripeRedirectUrl("http://checkout.stripe.com/c/pay")).toBe(
      false,
    );
    expect(isAllowedStripeRedirectUrl("not a url")).toBe(false);
  });

  it("starts credit-pack checkout with pack-aware billing return URLs", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ checkout_url: "" });
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync,
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Buy Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
      }),
    );
    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        cancel_url: expect.any(String),
        credit_pack_id: "portfolio_5",
        success_url: expect.any(String),
      });
    });
    const checkoutRequest = mutateAsync.mock.calls[0]?.[0];
    expectBillingCreditReturnUrl(checkoutRequest.cancel_url, {
      checkout: "cancelled",
      creditPackId: "portfolio_5",
    });
    expectBillingCreditReturnUrl(checkoutRequest.success_url, {
      checkout: "success",
      creditPackId: "portfolio_5",
    });
  });

  it("keeps billing visible but disables spend actions for non-admin roles", () => {
    mockBillingAuth.hasClerk = true;
    mockBillingAuth.orgRole = "org:member";
    mockStarterBillingAccount();
    const planCheckout = vi.fn().mockResolvedValue({ checkout_url: "" });
    const creditCheckout = vi.fn().mockResolvedValue({ checkout_url: "" });
    const portalCheckout = vi.fn().mockResolvedValue({ portal_url: "" });
    mockUseCreateCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: planCheckout,
    });
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: creditCheckout,
    });
    mockUseCreatePortalSession.mockReturnValue({
      isPending: false,
      mutateAsync: portalCheckout,
    });

    render(<BillingPage />);

    expect(screen.getByText("Subscription status")).toBeInTheDocument();
    expect(
      screen.getByText("Prepaid Report Credit capacity"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Billing purchase controls require admin access"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Review support boundary" }),
    ).toHaveAttribute("href", "/help#contact");
    const manageSubscription = screen.getByRole("button", {
      name: /Manage Subscription/i,
    });
    const upgradeToPro = screen.getByRole("button", {
      name: "Upgrade to Pro",
    });
    const buySingleCredit = screen.getByRole("button", {
      name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
    });
    expect(manageSubscription).toBeDisabled();
    expect(upgradeToPro).toBeDisabled();
    expect(buySingleCredit).toBeDisabled();

    fireEvent.click(manageSubscription);
    fireEvent.click(upgradeToPro);
    fireEvent.click(buySingleCredit);

    expect(portalCheckout).not.toHaveBeenCalled();
    expect(planCheckout).not.toHaveBeenCalled();
    expect(creditCheckout).not.toHaveBeenCalled();
  });

  it("uses the authoritative API capability when it is stricter than the local role fallback", () => {
    mockBillingAuth.hasClerk = false;
    mockStarterBillingAccount();
    mockUseBillingStatus.mockReturnValue({
      ...mockUseBillingStatus(),
      data: {
        ...mockUseBillingStatus().data,
        can_manage_billing: false,
      },
    });

    render(<BillingPage />);

    expect(screen.getByTestId("billing-action-access-notice")).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
      }),
    ).toBeDisabled();
  });

  it("passes safe launch return paths into credit-pack checkout", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ checkout_url: "" });
    mockSearchParams = new URLSearchParams(
      "intent=credits&pack=portfolio_5&return_to=%2Fanalyses%2Fnew%3Fresume%3Dcredit_checkout%26launch_draft_id%3Dld_checkout_123",
    );
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync,
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Buy Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
      }),
    );

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        cancel_url: `${window.location.origin}/analyses/new?resume=credit_checkout&launch_draft_id=ld_checkout_123&checkout=cancelled&credit_pack=portfolio_5&intent=credits`,
        credit_pack_id: "portfolio_5",
        success_url: `${window.location.origin}/analyses/new?resume=credit_checkout&launch_draft_id=ld_checkout_123&checkout=success&credit_pack=portfolio_5&intent=credits`,
      });
    });
  });

  it("preserves launch drafts when existing capacity covers a credit intent", () => {
    const launchReturnPath =
      "/analyses/new?resume=credit_checkout&launch_draft_id=ld_resume_123";
    mockSearchParams = new URLSearchParams({
      intent: "credits",
      pack: "portfolio_5",
      return_to: launchReturnPath,
    });

    render(<BillingPage />);

    for (const link of screen.getAllByRole("link", {
      name: "Start analysis using existing capacity",
    })) {
      expect(link).toHaveAttribute("href", launchReturnPath);
    }
  });

  it("keeps client billing viewers away from analysis-launch destinations", () => {
    mockPrincipalState.canCreateAnalysis = false;
    mockSearchParams = new URLSearchParams(
      "intent=credits&pack=portfolio_5&return_to=%2Fanalyses%2Fnew",
    );

    render(<BillingPage />);

    expect(
      screen.queryByRole("link", {
        name: "Start analysis using existing capacity",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Start analysis" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByText(
        "This role can review capacity but cannot start a new analysis.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("preserves public pricing credit intent through Stripe return URLs", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ checkout_url: "" });
    mockSearchParams = new URLSearchParams(
      "intent=credits&needed_reports=5&pack=portfolio_5",
    );
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync,
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Buy Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
      }),
    );

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        cancel_url: `${window.location.origin}/billing?intent=credits&needed_reports=5&pack=portfolio_5&checkout=cancelled&credit_pack=portfolio_5`,
        credit_pack_id: "portfolio_5",
        success_url: `${window.location.origin}/billing?intent=credits&needed_reports=5&pack=portfolio_5&checkout=success&credit_pack=portfolio_5`,
      });
    });
  });

  it("ignores unsafe credit checkout return paths", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ checkout_url: "" });
    mockSearchParams = new URLSearchParams(
      "intent=credits&pack=portfolio_5&return_to=https%3A%2F%2Fevil.example%2Fresume",
    );
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync,
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Buy Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
      }),
    );

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        cancel_url: `${window.location.origin}/billing?intent=credits&pack=portfolio_5&checkout=cancelled&credit_pack=portfolio_5`,
        credit_pack_id: "portfolio_5",
        success_url: `${window.location.origin}/billing?intent=credits&pack=portfolio_5&checkout=success&credit_pack=portfolio_5`,
      });
    });
    expect(mutateAsync.mock.calls[0]?.[0].success_url).not.toContain(
      "evil.example",
    );
  });

  it("does not use unsafe launch return paths for covered-capacity links", () => {
    mockSearchParams = new URLSearchParams(
      "intent=credits&pack=portfolio_5&return_to=https%3A%2F%2Fevil.example%2Fresume",
    );

    render(<BillingPage />);

    for (const link of screen.getAllByRole("link", {
      name: "Start analysis using existing capacity",
    })) {
      expect(link).toHaveAttribute("href", "/analyses/new");
    }
  });

  it("locks plan and portal actions while credit checkout is opening", async () => {
    mockStarterBillingAccount();
    const planCheckout = vi.fn().mockResolvedValue({ checkout_url: "" });
    const portalCheckout = vi.fn().mockResolvedValue({ portal_url: "" });
    const creditCheckout = vi.fn().mockReturnValue(new Promise(() => {}));
    mockUseCreateCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: planCheckout,
    });
    mockUseCreatePortalSession.mockReturnValue({
      isPending: false,
      mutateAsync: portalCheckout,
    });
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: creditCheckout,
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
      }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Manage Subscription/i }),
      ).toBeDisabled();
    });
    expect(
      screen.getByRole("button", { name: "Upgrade to Pro" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Review Report Credit Packs" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", {
        name: /Buy buffer .* Report Credit/i,
      }),
    ).not.toBeInTheDocument();
    const estimator = screen.getByRole("region", {
      name: "Match Report Credits to demand",
    });
    expect(estimator).toHaveAttribute("aria-busy", "true");
    expect(
      within(estimator).getByText("Opening checkout for Single Report Credit."),
    ).toBeInTheDocument();
    expect(
      within(estimator).getByRole("button", { name: "15 reports" }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Upgrade to Pro" }));
    fireEvent.click(
      screen.getByRole("button", { name: /Manage Subscription/i }),
    );

    expect(creditCheckout).toHaveBeenCalledTimes(1);
    expect(planCheckout).not.toHaveBeenCalled();
    expect(portalCheckout).not.toHaveBeenCalled();
  });

  it("locks credit and plan actions while the subscription portal is opening", async () => {
    mockStarterBillingAccount();
    const planCheckout = vi.fn().mockResolvedValue({ checkout_url: "" });
    const creditCheckout = vi.fn().mockResolvedValue({ checkout_url: "" });
    const portalCheckout = vi.fn().mockReturnValue(new Promise(() => {}));
    mockUseCreateCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: planCheckout,
    });
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: creditCheckout,
    });
    mockUseCreatePortalSession.mockReturnValue({
      isPending: false,
      mutateAsync: portalCheckout,
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", { name: /Manage Subscription/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Manage Subscription/i }),
      ).toBeDisabled();
    });
    expect(
      screen.getByRole("button", { name: "Upgrade to Pro" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
      }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Upgrade to Pro" }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
      }),
    );

    expect(portalCheckout).toHaveBeenCalledTimes(1);
    expect(planCheckout).not.toHaveBeenCalled();
    expect(creditCheckout).not.toHaveBeenCalled();
  });

  it("highlights a public credit-pack deep link without skipping the checkout review", () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    mockSearchParams = new URLSearchParams("intent=credits&pack=diligence_15");

    render(<BillingPage />);

    expect(screen.getByText("Selected from pricing:")).toBeInTheDocument();
    expect(
      screen.getByText(/Diligence Pack is highlighted below\./i),
    ).toBeInTheDocument();
    const selectedPack = screen.getByRole("article", {
      name: /Diligence Pack, 15 Report Credits for \$3,175, Diligence sprint, \$560 saved/i,
    });
    expect(selectedPack).toHaveClass("ring-brand-primary/35");

    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(selectedPack).not.toHaveFocus();
  });

  it("seeds the credit estimator from launch demand links", () => {
    mockSearchParams = new URLSearchParams(
      "intent=credits&needed_reports=1&pack=single_analysis",
    );

    render(<BillingPage />);

    const estimator = screen.getByRole("region", {
      name: "Match Report Credits to demand",
    });
    expect(
      within(estimator).getByRole("button", { name: "1 report" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(estimator).getByText("Recommendation for 1 report"),
    ).toBeInTheDocument();
    expect(
      within(estimator).getByText("No purchase needed"),
    ).toBeInTheDocument();
  });

  it("places a checkout hero before account admin for credit intent", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ checkout_url: "" });
    mockSearchParams = new URLSearchParams(
      "intent=credits&needed_reports=1&pack=single_analysis",
    );
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync,
    });

    render(<BillingPage />);

    const checkoutHero = screen.getByTestId("billing-credit-intent-hero");
    const accountHeader = screen.getByTestId("billing-app-surface-header");
    expect(
      checkoutHero.compareDocumentPosition(accountHeader) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(checkoutHero).toHaveTextContent("Report Credit checkout");
    expect(checkoutHero).toHaveTextContent("Single Report Credit for $249");
    expect(checkoutHero).toHaveTextContent(
      "85 Report Credits already covers 1 Report Credit",
    );
    expect(checkoutHero).toHaveTextContent("One-time Stripe checkout");
    expect(checkoutHero).toHaveTextContent("Included credits used first");
    expect(checkoutHero).toHaveTextContent("Tax and receipt in Stripe");
    expect(checkoutHero).toHaveTextContent(
      "First-pass request, not a legal conclusion",
    );
    expect(checkoutHero.querySelector("dl")).toHaveClass(
      "grid-cols-1",
      "min-[360px]:grid-cols-3",
    );

    const existingCapacityLink = within(checkoutHero).getByRole("link", {
      name: "Start analysis using existing capacity",
    });
    expect(existingCapacityLink).toHaveAttribute("href", "/analyses/new");
    expect(existingCapacityLink).toHaveClass("whitespace-normal", "leading-5");

    fireEvent.click(
      within(checkoutHero).getByRole("button", {
        name: "Buy buffer Single Report Credit, 1 Report Credit for $249",
      }),
    );
    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        cancel_url: `${window.location.origin}/billing?intent=credits&needed_reports=1&pack=single_analysis&checkout=cancelled&credit_pack=single_analysis`,
        credit_pack_id: "single_analysis",
        success_url: `${window.location.origin}/billing?intent=credits&needed_reports=1&pack=single_analysis&checkout=success&credit_pack=single_analysis`,
      });
    });
  });

  it("uses included launch capacity before nudging pay-as-you-go purchase", () => {
    mockSearchParams = new URLSearchParams(
      "intent=credits&needed_reports=1&pack=single_analysis",
    );
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "starter",
        stripe_customer_id: "cus_123",
        stripe_subscription_id: "sub_123",
        subscription_status: "active",
        current_period_start: "2026-04-01T00:00:00.000Z",
        current_period_end: "2026-05-01T00:00:00.000Z",
        analyses_used: 4,
        analyses_limit: 25,
        included_analyses_limit: 25,
        purchased_credits_balance: 0,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "starter",
        analyses_used: 4,
        analyses_limit: 25,
        included_analyses_limit: 25,
        purchased_credits_balance: 0,
        usage_pct: 16,
        cost_this_month_cents: 0,
        overage_analyses: 0,
        period_start: "2026-04-01T00:00:00.000Z",
        period_end: "2026-05-01T00:00:00.000Z",
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    const checkoutHero = screen.getByTestId("billing-credit-intent-hero");
    expect(checkoutHero).toHaveTextContent(
      "21 Report Credits already covers 1 Report Credit",
    );
    expect(
      within(checkoutHero).getByRole("link", {
        name: "Start analysis using existing capacity",
      }),
    ).toHaveAttribute("href", "/analyses/new");
    const estimator = screen.getByRole("region", {
      name: "Match Report Credits to demand",
    });
    expect(estimator).toHaveTextContent(
      "Current capacity is 21 Report Credits, including 0 Report Credits purchased.",
    );
    expect(
      within(estimator).getByText(
        "Current launch capacity covers this run. Continue without checkout.",
      ),
    ).toBeInTheDocument();
    expect(
      within(estimator).getByRole("link", {
        name: "Start analysis using existing capacity",
      }),
    ).toBeInTheDocument();
  });

  it("ignores invalid public credit-pack deep links", () => {
    mockSearchParams = new URLSearchParams("intent=credits&pack=unknown_pack");

    render(<BillingPage />);

    expect(
      screen.queryByText("Selected from pricing:"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("article", {
        name: /Diligence Pack, 15 Report Credits for \$3,175, Diligence sprint, \$560 saved/i,
      }),
    ).not.toHaveClass("ring-brand-primary/35");
  });

  it("highlights valid demo credit-pack checkout returns", async () => {
    mockDemoRuntime.enabled = true;
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    mockSearchParams = new URLSearchParams("demo_credit_pack=portfolio_5");

    render(<BillingPage />);

    expect(
      screen.getByText("Credit checkout preview complete"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Portfolio Pack returned from demo checkout/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("status", { name: "Stripe reconciliation status" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Portfolio Pack preview ready"),
    ).toBeInTheDocument();
    expect(screen.getByText("+5 Report Credits")).toBeInTheDocument();
    expect(screen.getByText("$1,145 previewed")).toBeInTheDocument();
    expect(screen.getByText("Preview receipt mapped")).toBeInTheDocument();

    const selectedPack = screen.getByRole("article", {
      name: /Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
    });
    expect(selectedPack).toHaveClass("ring-brand-primary/35");

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "center" });
    });
    expect(selectedPack).toHaveFocus();
  });

  it("announces demo subscription checkout returns", () => {
    mockDemoRuntime.enabled = true;
    mockSearchParams = new URLSearchParams("demo_checkout=enterprise");

    render(<BillingPage />);

    expect(
      screen.getByText("Subscription checkout preview complete"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Demo checkout returned for the enterprise plan/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Checkout complete")).not.toBeInTheDocument();
  });

  it("ignores synthetic checkout return markers outside demo mode", () => {
    mockSearchParams = new URLSearchParams(
      "demo_checkout=enterprise&demo_credit_pack=portfolio_5&demo_portal=subscription",
    );

    render(<BillingPage />);

    expect(
      screen.queryByText("Subscription checkout preview complete"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Credit checkout preview complete"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Subscription portal preview"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("article", {
        name: /Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
      }),
    ).not.toHaveClass("ring-brand-primary/35");
  });

  it("keeps live credit-pack checkout confirmations in view", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    mockSearchParams = new URLSearchParams(
      "checkout=success&credit_pack=portfolio_5&intent=credits&checkout_session_id=cs_test_applied123",
    );
    mockUseCreditPackCheckoutReconciliation.mockReturnValue({
      data: {
        status: "applied",
        session_id: "cs_test_applied123",
        ledger_entry_id: "11111111-1111-4111-8111-111111111111",
        credit_pack_id: "single_analysis",
        credits_applied: 1,
        current_purchased_credits_balance: 7,
        applied_at: "2026-07-16T08:00:00.000Z",
      },
      error: null,
      isFetching: false,
      pollingTimedOut: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.queryByText("Checkout complete")).not.toBeInTheDocument();
    expect(
      screen.getByTestId("credit-reconciliation-applied"),
    ).toHaveTextContent("1 Report Credit applied");
    expect(
      screen.getByText(/Single Report Credit · 1 Report Credit/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/5 Report Credits applied/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText("7 Report Credits")).toBeInTheDocument();
    expect(
      screen.getByText(/Ledger 11111111-1111-4111-8111-111111111111/i),
    ).toBeInTheDocument();
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("defensively reconciles a valid credit session without the intent parameter", () => {
    mockSearchParams = new URLSearchParams(
      "checkout=success&checkout_session_id=cs_test_applied123",
    );
    mockUseCreditPackCheckoutReconciliation.mockReturnValue({
      data: {
        status: "applied",
        session_id: "cs_test_applied123",
        ledger_entry_id: "11111111-1111-4111-8111-111111111111",
        credit_pack_id: "single_analysis",
        credits_applied: 1,
        current_purchased_credits_balance: 7,
        applied_at: "2026-07-16T08:00:00.000Z",
      },
      error: null,
      isFetching: false,
      pollingTimedOut: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getByText("1 Report Credit applied")).toBeInTheDocument();
    expect(screen.queryByText("Checkout returned")).not.toBeInTheDocument();
  });

  it("does not reconcile a cancelled live credit-pack checkout", () => {
    mockSearchParams = new URLSearchParams(
      "checkout=cancelled&credit_pack=portfolio_5&intent=credits",
    );

    render(<BillingPage />);

    expect(screen.getByText("Checkout flow cancelled")).toBeInTheDocument();
    expect(
      screen.queryByText("Report Credit checkout returned"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Portfolio Pack purchase is reconciling"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("+5 Report Credits")).not.toBeInTheDocument();
  });

  it("shows capacity runway and reviews packs before starting checkout", () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    const mutateAsync = vi.fn().mockResolvedValue({ checkout_url: "" });
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync,
    });

    render(<BillingPage />);

    expect(screen.getByText("Billing governance")).toBeInTheDocument();
    const governance = screen.getByRole("complementary", {
      name: "Billing governance controls",
    });
    expect(
      within(governance).getByText(/Praviar does not store card details/),
    ).toBeInTheDocument();
    expect(screen.getByText("Capacity runway")).toBeInTheDocument();
    expect(screen.getByText("85 Report Credits left")).toBeInTheDocument();
    expect(
      screen.getByText("79 included, 6 Report Credits"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Purchased Report Credits apply after plan allowance"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("billing-capacity-runway-field")).toHaveClass(
      "praviar-capacity-runway-field",
    );
    const layoutClasses = screen
      .getByTestId("billing-capacity-runway-layout")
      .className.split(/\s+/);
    expect(layoutClasses).toContain(
      "2xl:grid-cols-[minmax(13rem,0.55fr)_minmax(0,34rem)_auto]",
    );
    expect(layoutClasses).not.toContain("xl:grid-cols-[minmax(0,1fr)_auto]");

    fireEvent.click(
      screen.getByRole("button", { name: "Review Report Credit Packs" }),
    );
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "start",
      behavior: "smooth",
    });
    expect(scrollIntoView.mock.contexts[0]).toBe(
      document.getElementById("credit-pack-options"),
    );
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("respects reduced motion when reviewing credit packs", () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", { name: "Review Report Credit Packs" }),
    );
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "start",
      behavior: "auto",
    });
    window.matchMedia = originalMatchMedia;
  });

  it("keeps zero included allowance distinct from purchased Report Credits", () => {
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        stripe_customer_id: null,
        stripe_subscription_id: null,
        subscription_status: null,
        current_period_start: null,
        current_period_end: null,
        analyses_used: 0,
        analyses_limit: 5,
        included_analyses_limit: 0,
        purchased_credits_balance: 5,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        analyses_used: 0,
        analyses_limit: 5,
        included_analyses_limit: 0,
        purchased_credits_balance: 5,
        usage_pct: 0,
        cost_this_month_cents: 0,
        overage_analyses: 0,
        period_start: null,
        period_end: null,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getByText("0 included first")).toBeInTheDocument();
    expect(
      screen.getByText("0 included, 5 Report Credits"),
    ).toBeInTheDocument();
  });

  it("uses singular credit copy in the capacity runway", () => {
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        stripe_customer_id: null,
        stripe_subscription_id: null,
        subscription_status: null,
        current_period_start: null,
        current_period_end: null,
        analyses_used: 0,
        analyses_limit: 1,
        included_analyses_limit: 0,
        purchased_credits_balance: 1,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        analyses_used: 0,
        analyses_limit: 1,
        included_analyses_limit: 0,
        purchased_credits_balance: 1,
        usage_pct: 0,
        cost_this_month_cents: 0,
        overage_analyses: 0,
        period_start: null,
        period_end: null,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    expect(screen.getByText("0 included, 1 Report Credit")).toBeInTheDocument();
    expect(screen.queryByText("1 Report Credits")).not.toBeInTheDocument();
  });

  it("shows exhausted capacity rather than unset capacity for pay-as-you-go accounts", () => {
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        stripe_customer_id: null,
        stripe_subscription_id: null,
        subscription_status: null,
        current_period_start: null,
        current_period_end: null,
        analyses_used: 0,
        analyses_limit: 0,
        included_analyses_limit: 0,
        purchased_credits_balance: 0,
        cancel_at_period_end: false,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseUsageSummary.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "free",
        analyses_used: 0,
        analyses_limit: 0,
        included_analyses_limit: 0,
        purchased_credits_balance: 0,
        usage_pct: 0,
        cost_this_month_cents: 0,
        overage_analyses: 0,
        period_start: null,
        period_end: null,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<BillingPage />);

    const capacityRunway = screen.getByRole("region", {
      name: "Capacity runway",
    });
    expect(
      within(capacityRunway).getByText("0 Report Credits left"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Capacity is exhausted. Buy Report Credits before launching more FTO work.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Buy Report Credits" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Capacity not set")).not.toBeInTheDocument();
  });

  it("sanitizes credit-pack checkout failures", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockRejectedValue(new Error("stripe secret leaked")),
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
      }),
    );
    await waitFor(() =>
      expect(useToastStore.getState().toasts[0]).toMatchObject({
        message:
          "Could not start credit checkout. No credits have been purchased.",
        type: "error",
      }),
    );
    const inlineError = screen.getByTestId("billing-action-error-notice");
    const billingNarrative = screen.getByTestId("billing-page-narrative");
    expect(inlineError).toHaveTextContent("Checkout not started");
    expect(inlineError).toHaveTextContent(
      "No credits have been purchased, and the workspace ledger is unchanged.",
    );
    expect(
      within(inlineError).getByRole("button", { name: "Retry checkout" }),
    ).toHaveClass("min-h-11");
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({
        behavior: "auto",
        block: "start",
      });
    });
    expect(scrollIntoView.mock.contexts).toContain(billingNarrative);
    expect(billingNarrative).toHaveClass("scroll-mt-20", "space-y-6");
    expect(consoleError).toHaveBeenCalledWith(
      "[BillingPage] Failed to start credit checkout",
    );
    expect(screen.queryByText(/stripe secret leaked/i)).not.toBeInTheDocument();
    consoleError.mockRestore();
  });

  it("fails closed when plan checkout returns an empty redirect URL", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCreateCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockResolvedValue({ checkout_url: "   " }),
    });
    mockStarterBillingAccount();

    render(<BillingPage />);

    fireEvent.click(screen.getByRole("button", { name: "Upgrade to Pro" }));

    await waitFor(() =>
      expect(useToastStore.getState().toasts[0]).toMatchObject({
        message: "Could not start checkout. No plan changes have been made.",
        type: "error",
      }),
    );
    expect(screen.getByTestId("billing-action-error-notice")).toHaveTextContent(
      "Plan checkout did not start",
    );
    expect(consoleError).toHaveBeenCalledWith(
      "[BillingPage] Failed to start checkout",
    );
    consoleError.mockRestore();
  });

  it("fails closed when the subscription portal returns an empty redirect URL", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCreatePortalSession.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockResolvedValue({ portal_url: "" }),
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", { name: /Manage Subscription/i }),
    );

    await waitFor(() =>
      expect(useToastStore.getState().toasts[0]).toMatchObject({
        message:
          "Could not open the subscription portal. Your subscription is unchanged.",
        type: "error",
      }),
    );
    expect(screen.getByTestId("billing-action-error-notice")).toHaveTextContent(
      "Subscription portal did not open",
    );
    expect(consoleError).toHaveBeenCalledWith(
      "[BillingPage] Failed to open subscription portal",
    );
    consoleError.mockRestore();
  });

  it("fails closed when credit checkout returns an empty redirect URL", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockResolvedValue({ checkout_url: "" }),
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
      }),
    );

    await waitFor(() =>
      expect(useToastStore.getState().toasts[0]).toMatchObject({
        message:
          "Could not start credit checkout. No credits have been purchased.",
        type: "error",
      }),
    );
    expect(screen.getByTestId("billing-action-error-notice")).toHaveTextContent(
      "Checkout not started",
    );
    expect(consoleError).toHaveBeenCalledWith(
      "[BillingPage] Failed to start credit checkout",
    );
    consoleError.mockRestore();
  });

  it("re-enables billing actions after an unsafe credit checkout redirect", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCreateCreditPackCheckout.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockResolvedValue({
        checkout_url: "https://evil.example/checkout",
      }),
    });

    render(<BillingPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
      }),
    );

    await waitFor(() =>
      expect(useToastStore.getState().toasts[0]).toMatchObject({
        message:
          "Could not start credit checkout. No credits have been purchased.",
        type: "error",
      }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: "Buy Single Report Credit, 1 Report Credit for $249, One-off analysis",
        }),
      ).not.toBeDisabled();
    });
    expect(
      screen.getByRole("button", { name: /Manage Subscription/i }),
    ).not.toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Review Report Credit Packs" }),
    ).not.toBeDisabled();
    expect(consoleError).toHaveBeenCalledWith(
      "[BillingPage] Failed to start credit checkout",
    );
    consoleError.mockRestore();
  });
});
