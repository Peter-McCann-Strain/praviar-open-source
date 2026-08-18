import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockApiClient = vi.hoisted(() => vi.fn());

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => null,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: mockApiClient,
}));

import { useAdminHealth, useAdminMetrics } from "@/hooks/use-admin";
import {
  useCostAnalytics,
  useUsageAnalytics,
} from "@/hooks/use-admin-analytics";
import {
  useCreateAPIKey,
  useAPIKeys,
  useRevokeAPIKey,
} from "@/hooks/use-api-keys";
import {
  useBillingStatus,
  useCreateCheckout,
  useCreateCreditPackCheckout,
  useCreatePortalSession,
  useInvoices,
  useUsageSummary,
  type CheckoutResponse,
} from "@/hooks/use-billing";
import { useConfigureSSO, useSSOStatus } from "@/hooks/use-sso";
import type { APIKeyCreatedResponse } from "@/hooks/use-api-keys";

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

describe("platform controls in demo mode", () => {
  beforeEach(() => {
    mockApiClient.mockClear();
  });

  it("serves billing status, usage, invoices, and checkout locally", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        status: useBillingStatus(null),
        usage: useUsageSummary(null),
        invoices: useInvoices(null),
        checkout: useCreateCheckout(null),
        creditPackCheckout: useCreateCreditPackCheckout(null),
        portal: useCreatePortalSession(null),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.status.isSuccess).toBe(true));
    await waitFor(() => expect(result.current.usage.isSuccess).toBe(true));
    await waitFor(() => expect(result.current.invoices.isSuccess).toBe(true));

    expect(result.current.status.data?.plan).toBe("pro");
    expect(result.current.status.data?.current_period_start).toBe(
      "2026-07-01T00:00:00.000Z",
    );
    expect(result.current.status.data?.current_period_end).toBe(
      "2026-08-01T00:00:00.000Z",
    );
    expect(result.current.usage.data?.usage_pct).toBe(19.8);
    expect(result.current.usage.data?.period_start).toBe(
      "2026-07-01T00:00:00.000Z",
    );
    expect(result.current.usage.data?.period_end).toBe(
      "2026-08-01T00:00:00.000Z",
    );
    expect(result.current.invoices.data?.invoices[0]?.number).toBe(
      "SG-2026-0042",
    );
    expect(result.current.invoices.data?.invoices[0]?.created_at).toBe(
      "2026-07-01T00:00:00.000Z",
    );
    expect(
      result.current.invoices.data?.invoices[0]?.hosted_invoice_url,
    ).toBeNull();
    expect(result.current.invoices.data?.invoices[0]?.pdf_url).toBeNull();

    let checkout: CheckoutResponse | null = null;
    await act(async () => {
      checkout = await result.current.checkout.mutateAsync({
        plan_id: "enterprise",
      });
    });

    expect(checkout?.checkout_url).toBe("/billing?demo_checkout=enterprise");

    let creditCheckout: CheckoutResponse | null = null;
    await act(async () => {
      creditCheckout = await result.current.creditPackCheckout.mutateAsync({
        credit_pack_id: "portfolio_5",
      });
    });

    expect(creditCheckout?.checkout_url).toBe(
      "/billing?demo_credit_pack=portfolio_5",
    );

    let portal: Awaited<
      ReturnType<typeof result.current.portal.mutateAsync>
    > | null = null;
    await act(async () => {
      portal = await result.current.portal.mutateAsync();
    });

    expect(portal?.portal_url).toBe("/billing?demo_portal=subscription");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves and creates API keys locally", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        keys: useAPIKeys(),
        createKey: useCreateAPIKey(),
        revokeKey: useRevokeAPIKey(),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.keys.isSuccess).toBe(true));
    expect(result.current.keys.data?.items[0]?.name).toBe(
      "Production case workspace API",
    );
    const existingKeyId = result.current.keys.data?.items[0]?.id;

    let created: APIKeyCreatedResponse | null = null;
    await act(async () => {
      created = await result.current.createKey.mutateAsync({
        name: "Demo integration",
      });
    });

    expect(created?.secret_key).toMatch(/^sg_demo_/);
    await act(async () => {
      await result.current.revokeKey.mutateAsync(
        existingKeyId ?? "key_demo_001",
      );
    });
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves SSO status and configure flow locally", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        status: useSSOStatus(),
        configure: useConfigureSSO(),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.status.isSuccess).toBe(true));
    expect(result.current.status.data?.status).toBe("inactive");

    let response: Awaited<
      ReturnType<typeof result.current.configure.mutateAsync>
    > | null = null;
    await act(async () => {
      response = await result.current.configure.mutateAsync(true);
    });

    expect(response?.status).toBe("pending");
    expect(response?.next_steps.length).toBeGreaterThan(0);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("serves admin and analytics data locally", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => ({
        health: useAdminHealth(),
        metrics: useAdminMetrics(),
        costs: useCostAnalytics("month"),
        usage: useUsageAnalytics("month"),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.health.isSuccess).toBe(true));
    await waitFor(() => expect(result.current.costs.isSuccess).toBe(true));

    expect(result.current.health.data?.services[0]?.name).toBe("api");
    expect(result.current.metrics.data?.total_analyses).toBeGreaterThan(0);
    expect(result.current.costs.data?.total_cost_usd).toBeGreaterThan(0);
    expect(result.current.usage.data?.top_compounds[0]?.compound_name).toBe(
      "Succinic acid",
    );
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
