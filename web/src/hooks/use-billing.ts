"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  authScopeKey,
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";

// ── Types ──────────────────────────────────────────────────────────────────

export type PlanTier = "free" | "starter" | "pro" | "enterprise";
export type CreditPackId =
  | "single_analysis"
  | "portfolio_5"
  | "diligence_15"
  | "scale_30";

export interface BillingStatus {
  org_id: string;
  can_manage_billing?: boolean;
  plan: PlanTier;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  subscription_status: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  analyses_used: number;
  analyses_limit: number;
  included_analyses_limit: number;
  purchased_credits_balance: number;
  purchased_credits_used: number;
  cancel_at_period_end: boolean;
}

export interface UsageSummary {
  org_id: string;
  plan: PlanTier;
  analyses_used: number;
  analyses_limit: number;
  included_analyses_limit: number;
  purchased_credits_balance: number;
  purchased_credits_used: number;
  usage_pct: number;
  cost_this_month_cents: number;
  overage_analyses: number;
  period_start: string | null;
  period_end: string | null;
}

export interface InvoiceItem {
  id: string;
  number: string | null;
  status: string;
  amount_due_cents: number;
  amount_paid_cents: number;
  currency: string;
  created_at: string;
  hosted_invoice_url: string | null;
  pdf_url: string | null;
}

export interface InvoiceListResponse {
  invoices: InvoiceItem[];
  has_more: boolean;
}

export interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export type CreditCapacityRequestSource =
  | "analysis_launch"
  | "capacity_watch"
  | "launch_retry";

export interface CreditCapacityRequestResponse {
  notified_admins: number;
  request_id: string;
  requested_at: string;
  status: "sent";
}

export type CreditCapacityRequestStatus = "pending" | "fulfilled" | "declined";

export interface CreditCapacityRequestItem {
  id: string;
  requester_user_id: string | null;
  requester_name: string;
  requested_reports: number;
  source: CreditCapacityRequestSource;
  status: CreditCapacityRequestStatus;
  notified_admins: number;
  requested_at: string;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
  resolution_note: string | null;
  fulfillment_credit_ledger_id: string | null;
  resolution_outcome?: "resolved" | "already_resolved" | null;
}

export interface CreditCapacityRequestListResponse {
  items: CreditCapacityRequestItem[];
  total: number;
  page: number;
  per_page: number;
}

export type CreditPackCheckoutReconciliation =
  | {
      status: "pending";
      session_id: string;
    }
  | {
      status: "applied";
      session_id: string;
      ledger_entry_id: string;
      credit_pack_id: CreditPackId;
      credits_applied: number;
      current_purchased_credits_balance: number;
      applied_at: string;
    };

export interface PortalResponse {
  portal_url: string;
}

const CREDIT_RECONCILIATION_POLL_INTERVAL_MS = 2_000;
const CREDIT_RECONCILIATION_POLL_LIMIT_MS = 60_000;
const STRIPE_CHECKOUT_SESSION_ID_PATTERN = /^cs_(?:test|live)_[A-Za-z0-9]+$/u;

export function isStripeCheckoutSessionId(
  value: string | null | undefined,
): value is string {
  return Boolean(value && STRIPE_CHECKOUT_SESSION_ID_PATTERN.test(value));
}

// ── Demo fixtures ──────────────────────────────────────────────────────────

const DEMO_BILLING_STATUS: BillingStatus = {
  org_id: "org_demo_001",
  can_manage_billing: true,
  plan: "pro",
  stripe_customer_id: "cus_demo_pro",
  stripe_subscription_id: "sub_demo_pro",
  subscription_status: "active",
  current_period_start: "2026-07-01T00:00:00.000Z",
  current_period_end: "2026-08-01T00:00:00.000Z",
  analyses_used: 21,
  analyses_limit: 106,
  included_analyses_limit: 100,
  purchased_credits_balance: 6,
  purchased_credits_used: 0,
  cancel_at_period_end: false,
};

const DEMO_USAGE_SUMMARY: UsageSummary = {
  org_id: "org_demo_001",
  plan: "pro",
  analyses_used: 21,
  analyses_limit: 106,
  included_analyses_limit: 100,
  purchased_credits_balance: 6,
  purchased_credits_used: 0,
  usage_pct: 19.8,
  cost_this_month_cents: 18_400,
  overage_analyses: 0,
  period_start: "2026-07-01T00:00:00.000Z",
  period_end: "2026-08-01T00:00:00.000Z",
};

const DEMO_INVOICES: InvoiceListResponse = {
  invoices: [
    {
      id: "in_demo_0042",
      number: "SG-2026-0042",
      status: "paid",
      amount_due_cents: 49900,
      amount_paid_cents: 49900,
      currency: "usd",
      created_at: "2026-07-01T00:00:00.000Z",
      hosted_invoice_url: null,
      pdf_url: null,
    },
  ],
  has_more: false,
};

// ── Hooks ──────────────────────────────────────────────────────────────────

/**
 * Fetch current org billing status (plan, subscription, usage).
 */
export function useBillingStatus(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(["billing", "status"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_BILLING_STATUS);
      }
      return apiClient<BillingStatus>("/billing/status", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

/**
 * Create a Stripe Checkout session for plan upgrade.
 */
export function useCreateCheckout(token: string | null) {
  return useMutation({
    mutationFn: (data: {
      plan_id: PlanTier;
      success_url?: string;
      cancel_url?: string;
    }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<CheckoutResponse>({
          checkout_url: `/billing?demo_checkout=${data.plan_id}`,
          session_id: `cs_demo_${data.plan_id}`,
        });
      }
      if (!token) {
        throw new Error("Authenticated plan checkout requires a token.");
      }
      return apiClient<CheckoutResponse>("/billing/checkout", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      });
    },
    // The billing page's handleUpgrade already surfaces checkout failures with
    // its own toast. Suppress the global MutationCache toast so a failed
    // checkout does not raise two error toasts.
    meta: { suppressGlobalErrorToast: true },
  });
}

/**
 * Create a Stripe Checkout session for one-time Report Credit Packs.
 */
export function useCreateCreditPackCheckout(token: string | null) {
  return useMutation({
    mutationFn: (data: {
      credit_pack_id: CreditPackId;
      success_url?: string;
      cancel_url?: string;
    }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<CheckoutResponse>({
          checkout_url: `/billing?demo_credit_pack=${data.credit_pack_id}`,
          session_id: `cs_demo_credit_${data.credit_pack_id}`,
        });
      }
      if (!token) {
        throw new Error("Authenticated credit checkout requires a token.");
      }
      return apiClient<CheckoutResponse>("/billing/credit-packs/checkout", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      });
    },
    meta: { suppressGlobalErrorToast: true },
  });
}

/**
 * Notify active workspace administrators that Report Credit capacity is needed.
 */
export function useRequestCreditCapacity(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: {
      requested_reports: number;
      source: CreditCapacityRequestSource;
    }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<CreditCapacityRequestResponse>({
          notified_admins: 1,
          request_id: "00000000-0000-4000-8000-000000000001",
          requested_at: new Date().toISOString(),
          status: "sent",
        });
      }
      if (!token) {
        throw new Error(
          "Authenticated Report Credit requests require a token.",
        );
      }
      return apiClient<CreditCapacityRequestResponse>(
        "/billing/credit-capacity-requests",
        {
          method: "POST",
          body: JSON.stringify(data),
          token,
        },
      );
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      invalidateAuthScopedQueries(
        queryClient,
        ["billing", "credit-capacity-requests"],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["notifications"], token);
    },
  });
}

/** List durable Report Credit requests visible to the current role. */
export function useCreditCapacityRequests(
  token: string | null,
  {
    enabled = true,
    page = 1,
    perPage = 20,
    status,
  }: {
    enabled?: boolean;
    page?: number;
    perPage?: number;
    status?: CreditCapacityRequestStatus;
  } = {},
) {
  return useQuery({
    queryKey: authScopedQueryKey(
      [
        "billing",
        "credit-capacity-requests",
        page,
        perPage,
        status ?? "all",
      ] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<CreditCapacityRequestListResponse>({
          items: [],
          total: 0,
          page,
          per_page: perPage,
        });
      }
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(perPage),
      });
      if (status) {
        params.set("status", status);
      }
      return apiClient<CreditCapacityRequestListResponse>(
        `/billing/credit-capacity-requests?${params}`,
        {
          token: token || undefined,
          signal,
        },
      );
    },
    enabled: enabled && (DEMO_MODE_ENABLED || !!token),
  });
}

/** Resolve one pending Report Credit request as a billing administrator. */
export function useResolveCreditCapacityRequest(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      requestId,
      status,
      note,
    }: {
      requestId: string;
      status: Exclude<CreditCapacityRequestStatus, "pending">;
      note?: string;
    }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<CreditCapacityRequestItem>({
          id: requestId,
          requester_user_id: "demo-user",
          requester_name: "Demo scientist",
          requested_reports: 1,
          source: "analysis_launch",
          status,
          notified_admins: 1,
          requested_at: new Date().toISOString(),
          resolved_at: new Date().toISOString(),
          resolved_by_user_id: "demo-admin",
          resolution_note: note ?? null,
          fulfillment_credit_ledger_id: null,
          resolution_outcome: "resolved",
        });
      }
      if (!token) {
        throw new Error(
          "Authenticated Report Credit resolution requires a token.",
        );
      }
      return apiClient<CreditCapacityRequestItem>(
        `/billing/credit-capacity-requests/${encodeURIComponent(requestId)}/resolve`,
        {
          method: "POST",
          body: JSON.stringify({ status, note: note?.trim() || null }),
          token,
        },
      );
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      invalidateAuthScopedQueries(
        queryClient,
        ["billing", "credit-capacity-requests"],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["notifications"], token);
    },
  });
}

/**
 * Poll the append-only Report Credit ledger for the exact current-user session.
 */
export function useCreditPackCheckoutReconciliation(
  token: string | null,
  sessionId: string | null,
) {
  const queryClient = useQueryClient();
  const validSessionId = isStripeCheckoutSessionId(sessionId)
    ? sessionId
    : null;
  const reconciliationAuthScope = authScopeKey(token);
  const reconciliationScope = validSessionId
    ? `${reconciliationAuthScope}:${validSessionId}`
    : null;
  const [pollScopeState, setPollScopeState] = useState<{
    activeScope: string | null;
    timedOutScope: string | null;
  }>({
    activeScope: null,
    timedOutScope: null,
  });
  const invalidatedAppliedSessionRef = useRef<string | null>(null);

  useEffect(() => {
    invalidatedAppliedSessionRef.current = null;
    const reset = window.setTimeout(() => {
      setPollScopeState({
        activeScope: reconciliationScope,
        timedOutScope: null,
      });
    }, 0);

    return () => window.clearTimeout(reset);
  }, [reconciliationScope]);

  const query = useQuery({
    queryKey: authScopedQueryKey(
      ["billing", "credit-pack-reconciliation", validSessionId] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (!token || !validSessionId) {
        throw new Error(
          "Authenticated Report Credit reconciliation requires a valid session.",
        );
      }
      return apiClient<CreditPackCheckoutReconciliation>(
        `/billing/credit-packs/reconciliation?session_id=${encodeURIComponent(validSessionId)}`,
        {
          token,
          signal,
        },
      );
    },
    enabled: !DEMO_MODE_ENABLED && Boolean(token && validSessionId),
    meta: { suppressGlobalErrorToast: true },
    refetchInterval: (currentQuery) => {
      if (
        currentQuery.state.data?.status !== "pending" ||
        (pollScopeState.activeScope === reconciliationScope &&
          pollScopeState.timedOutScope === reconciliationScope)
      ) {
        return false;
      }
      return CREDIT_RECONCILIATION_POLL_INTERVAL_MS;
    },
    refetchIntervalInBackground: false,
    retry: false,
  });

  useEffect(() => {
    if (
      !validSessionId ||
      query.data?.status !== "pending" ||
      query.data.session_id !== validSessionId ||
      !reconciliationScope ||
      pollScopeState.activeScope !== reconciliationScope
    ) {
      return undefined;
    }

    const timeout = window.setTimeout(() => {
      setPollScopeState((current) =>
        current.activeScope === reconciliationScope
          ? { ...current, timedOutScope: reconciliationScope }
          : current,
      );
    }, CREDIT_RECONCILIATION_POLL_LIMIT_MS);

    return () => window.clearTimeout(timeout);
  }, [
    query.data?.session_id,
    query.data?.status,
    pollScopeState.activeScope,
    reconciliationScope,
    validSessionId,
  ]);

  useEffect(() => {
    if (
      query.data?.status !== "applied" ||
      invalidatedAppliedSessionRef.current === query.data.session_id
    ) {
      return;
    }

    invalidatedAppliedSessionRef.current = query.data.session_id;
    invalidateAuthScopedQueries(queryClient, ["billing", "status"], token);
    invalidateAuthScopedQueries(queryClient, ["billing", "usage"], token);
    invalidateAuthScopedQueries(queryClient, ["billing", "invoices"], token);
    invalidateAuthScopedQueries(
      queryClient,
      ["billing", "credit-capacity-requests"],
      token,
    );
    invalidateAuthScopedQueries(queryClient, ["notifications"], token);
  }, [query.data, queryClient, token]);

  return {
    ...query,
    hasValidSessionId: Boolean(validSessionId),
    pollingTimedOut:
      query.data?.status === "pending" &&
      pollScopeState.activeScope === reconciliationScope &&
      pollScopeState.timedOutScope === reconciliationScope,
  };
}

/**
 * Create a Stripe Customer Portal session to manage subscription.
 */
export function useCreatePortalSession(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<PortalResponse>({
          portal_url: "/billing?demo_portal=subscription",
        });
      }
      if (!token) {
        throw new Error(
          "Authenticated billing portal access requires a token.",
        );
      }
      return apiClient<PortalResponse>("/billing/portal", {
        method: "POST",
        token,
      });
    },
    // The billing page's handleManageSubscription already toasts on failure;
    // suppress the global MutationCache toast to avoid a duplicate.
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      // Invalidate billing data when returning from portal
      invalidateAuthScopedQueries(queryClient, ["billing"], token);
    },
  });
}

/**
 * Fetch current month usage summary.
 */
export function useUsageSummary(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(["billing", "usage"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_USAGE_SUMMARY);
      }
      return apiClient<UsageSummary>("/billing/usage", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

/**
 * Fetch past invoices from Stripe.
 */
export function useInvoices(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(["billing", "invoices"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_INVOICES);
      }
      return apiClient<InvoiceListResponse>("/billing/invoices", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}
