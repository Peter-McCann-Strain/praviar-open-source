import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BillingHeader } from "@/components/billing/billing-header";
import { CreditPacksCard } from "@/components/billing/credit-packs-card";
import { CurrentPlanCard } from "@/components/billing/current-plan-card";
import {
  CREDIT_PACK_DETAILS,
  PLAN_INCLUDED_CREDITS,
  formatCents,
  formatCreditPackPrice,
  formatCurrency,
  formatDate,
  isCreditPackId,
  safeBillingDocumentHref,
} from "@/components/billing/helpers";
import { InvoiceHistoryCard } from "@/components/billing/invoice-history-card";
import { UpgradePlansCard } from "@/components/billing/upgrade-plans-card";
import { UsageCard } from "@/components/billing/usage-card";
import { UsageMeter } from "@/components/billing/usage-meter";
import type {
  BillingStatus,
  InvoiceListResponse,
  UsageSummary,
} from "@/hooks/use-billing";
import { APIError } from "@/lib/api-client";

const billingStatus: BillingStatus = {
  org_id: "org-1",
  plan: "pro",
  stripe_customer_id: "cus_123",
  stripe_subscription_id: "sub_123",
  subscription_status: "active",
  current_period_start: "2026-04-01T00:00:00.000Z",
  current_period_end: "2026-05-01T00:00:00.000Z",
  analyses_used: 42,
  analyses_limit: 100,
  included_analyses_limit: 100,
  purchased_credits_balance: 0,
  purchased_credits_used: 0,
  cancel_at_period_end: true,
};

const usageSummary: UsageSummary = {
  org_id: "org-1",
  plan: "starter",
  analyses_used: 26,
  analyses_limit: 25,
  included_analyses_limit: 25,
  purchased_credits_balance: 0,
  purchased_credits_used: 0,
  usage_pct: 100,
  cost_this_month_cents: 51_200,
  overage_analyses: 1,
  period_start: "2026-04-01T00:00:00.000Z",
  period_end: "2026-05-01T00:00:00.000Z",
};

function formatMarketingPackDetail(pack: {
  credits: number;
  priceCents: number;
}) {
  return `${formatCreditPackPrice(Math.round(pack.priceCents / pack.credits))} / request`;
}

describe("billing helpers", () => {
  it("formats money and nullable billing dates for invoice surfaces", () => {
    expect(formatCents(49_900)).toBe("$499.00");
    expect(formatCurrency(49_900, "eur")).toBe("€499.00");
    expect(formatCreditPackPrice(114_500)).toBe("$1,145");
    expect(formatCents(0)).toBe("$0.00");
    expect(formatDate(null)).toBe("N/A");
    expect(formatDate("2026-04-01T00:00:00.000Z")).toMatch(/Apr 1, 2026/);
  });

  it("allows only safe billing document links", () => {
    expect(safeBillingDocumentHref("https://billing.stripe.com/invoice")).toBe(
      "https://billing.stripe.com/invoice",
    );
    expect(safeBillingDocumentHref("https://invoice.stripe.com/i/demo")).toBe(
      "https://invoice.stripe.com/i/demo",
    );
    expect(
      safeBillingDocumentHref("https://pay.stripe.com/invoice/demo/pdf"),
    ).toBe("https://pay.stripe.com/invoice/demo/pdf");
    expect(
      safeBillingDocumentHref("/billing/invoices/in_demo_0042"),
    ).toBeUndefined();
    expect(safeBillingDocumentHref("javascript:alert(1)")).toBeUndefined();
    expect(safeBillingDocumentHref("data:text/html,hi")).toBeUndefined();
    expect(
      safeBillingDocumentHref("http://billing.example/invoice"),
    ).toBeUndefined();
    expect(
      safeBillingDocumentHref("https://evil.example/invoice"),
    ).toBeUndefined();
    expect(
      safeBillingDocumentHref("//billing.example/invoice"),
    ).toBeUndefined();
  });

  it("keeps authenticated checkout pack pricing internally consistent", () => {
    expect(
      formatCreditPackPrice(CREDIT_PACK_DETAILS.single_analysis.priceCents),
    ).toBe("$249");
    expect(PLAN_INCLUDED_CREDITS).toMatchObject({
      free: 2,
      starter: 25,
      pro: 100,
      enterprise: null,
    });
    expect(
      (["portfolio_5", "diligence_15", "scale_30"] as const).map((id) => ({
        label: `${CREDIT_PACK_DETAILS[id].credits} Report Credits`,
        price: formatCreditPackPrice(CREDIT_PACK_DETAILS[id].priceCents),
        detail: formatMarketingPackDetail(CREDIT_PACK_DETAILS[id]),
      })),
    ).toEqual([
      {
        label: "5 Report Credits",
        price: formatCreditPackPrice(
          CREDIT_PACK_DETAILS.portfolio_5.priceCents,
        ),
        detail: formatMarketingPackDetail(CREDIT_PACK_DETAILS.portfolio_5),
      },
      {
        label: "15 Report Credits",
        price: formatCreditPackPrice(
          CREDIT_PACK_DETAILS.diligence_15.priceCents,
        ),
        detail: formatMarketingPackDetail(CREDIT_PACK_DETAILS.diligence_15),
      },
      {
        label: "30 Report Credits",
        price: formatCreditPackPrice(CREDIT_PACK_DETAILS.scale_30.priceCents),
        detail: formatMarketingPackDetail(CREDIT_PACK_DETAILS.scale_30),
      },
    ]);
  });

  it("accepts only declared credit-pack ids from pricing query strings", () => {
    expect(isCreditPackId("portfolio_5")).toBe(true);
    expect(isCreditPackId("single_analysis")).toBe(true);
    expect(isCreditPackId("toString")).toBe(false);
    expect(isCreditPackId("__proto__")).toBe(false);
    expect(isCreditPackId(null)).toBe(false);
  });
});

describe("UsageMeter", () => {
  it("renders normal, near-limit, and overage states", () => {
    const { rerender } = render(<UsageMeter used={10} limit={25} pct={40} />);
    expect(screen.getByText("10 / 25")).toBeInTheDocument();
    expect(screen.queryByText("Approaching limit")).not.toBeInTheDocument();

    rerender(<UsageMeter used={22} limit={25} pct={88} />);
    expect(screen.getByText("Approaching limit")).toBeInTheDocument();

    rerender(<UsageMeter used={31} limit={25} pct={124} />);
    expect(screen.getByText("6 over limit")).toBeInTheDocument();
    expect(screen.queryByText("Approaching limit")).not.toBeInTheDocument();

    rerender(<UsageMeter used={21} limit={0} pct={0} limitConfigured />);
    expect(screen.getByText("21 / No limit set")).toBeInTheDocument();
    expect(screen.queryByText("21 over limit")).not.toBeInTheDocument();
    expect(screen.queryByText("Approaching limit")).not.toBeInTheDocument();
  });
});

describe("billing cards", () => {
  it("shows the current plan, subscription status, cancellation, and renewal date", () => {
    render(<CurrentPlanCard billingStatus={billingStatus} currentPlan="pro" />);

    expect(screen.getByText("Subscription status")).toBeInTheDocument();
    expect(screen.getByText("Current plan")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
    expect(screen.getByText("$1,499/mo")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Cancels at period end")).toBeInTheDocument();
    expect(screen.getByText(/May 1, 2026/)).toBeInTheDocument();
    expect(
      screen.getByText("API access subject to workspace review"),
    ).toBeInTheDocument();
  });

  it("does not invent a renewal period when no subscription is active", () => {
    render(
      <CurrentPlanCard
        currentPlan="free"
        billingStatus={{
          ...billingStatus,
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
        }}
      />,
    );

    expect(screen.getByText("No subscription")).toBeInTheDocument();
    expect(screen.getByText("No renewal scheduled")).toBeInTheDocument();
    expect(
      screen.getByText(
        "A renewal period appears after a subscription is active.",
      ),
    ).toBeInTheDocument();
  });

  it("does not render N/A as a renewal endpoint when only the start date exists", () => {
    render(
      <CurrentPlanCard
        currentPlan="pro"
        billingStatus={{
          ...billingStatus,
          current_period_end: null,
        }}
      />,
    );

    expect(screen.getByText("Started Apr 1, 2026")).toBeInTheDocument();
    expect(screen.queryByText(/N\/A/)).not.toBeInTheDocument();
  });

  it("renders usage ledger, billing period, and singular capacity copy", () => {
    render(<UsageCard usage={usageSummary} />);

    expect(screen.getByText("Usage ledger")).toBeInTheDocument();
    expect(screen.getByText("26 used")).toBeInTheDocument();
    expect(
      screen.getByText("25 included used, 1 over available credits"),
    ).toBeInTheDocument();
    expect(screen.queryByText("$512.00")).not.toBeInTheDocument();
    expect(screen.getByText(/Apr 1, 2026 - May 1, 2026/)).toBeInTheDocument();
    expect(
      screen.getByText("1 analysis beyond available Report Credits"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Buy Report Credits or adjust plan capacity before launching additional large FTO batches.",
      ),
    ).toBeInTheDocument();
  });

  it("distinguishes included usage from purchased credit burn", () => {
    render(
      <UsageCard
        usage={{
          ...usageSummary,
          analyses_used: 30,
          analyses_limit: 31,
          included_analyses_limit: 25,
          purchased_credits_balance: 1,
          purchased_credits_used: 5,
          usage_pct: 96.8,
          overage_analyses: 0,
        }}
      />,
    );

    expect(screen.getByText("30 used")).toBeInTheDocument();
    expect(
      screen.getByText("25 included used, 5 purchased credits used"),
    ).toBeInTheDocument();
    expect(screen.getByText("1 Report Credit")).toBeInTheDocument();
    expect(screen.getByText("1 purchased credit left")).toBeInTheDocument();
    expect(
      screen.queryByText("Counted against current included allowance"),
    ).not.toBeInTheDocument();
  });

  it("keeps purchased credits available after a lapsed plan allowance downgrade", () => {
    render(
      <UsageCard
        usage={{
          ...usageSummary,
          plan: "pro",
          analyses_used: 5,
          analyses_limit: 7,
          included_analyses_limit: 3,
          purchased_credits_balance: 2,
          purchased_credits_used: 0,
          usage_pct: 71.4,
          overage_analyses: 0,
        }}
      />,
    );

    expect(screen.getByText("5 used")).toBeInTheDocument();
    expect(
      screen.getByText("3 included used, 0 purchased credits used"),
    ).toBeInTheDocument();
    expect(screen.getByText("2 Report Credits")).toBeInTheDocument();
    expect(screen.getByText("2 purchased credits left")).toBeInTheDocument();
  });

  it("renders current-month defaults when usage has not loaded", () => {
    render(<UsageCard />);

    expect(screen.getByText("0 / No limit set")).toBeInTheDocument();
    expect(screen.getByText("0 used")).toBeInTheDocument();
    expect(screen.getAllByText("Usage data not loaded")).toHaveLength(2);
    expect(screen.getByText("Current month")).toBeInTheDocument();
    expect(screen.getByText("Not set")).toBeInTheDocument();
  });

  it("renders custom capacity without over-limit messaging", () => {
    render(
      <UsageCard
        usage={{
          ...usageSummary,
          plan: "enterprise",
          analyses_used: 21,
          analyses_limit: 0,
          included_analyses_limit: 0,
          usage_pct: 0,
          overage_analyses: 21,
        }}
      />,
    );

    expect(screen.getByText("21 / No limit set")).toBeInTheDocument();
    expect(screen.getByText("21 used")).toBeInTheDocument();
    expect(
      screen.getByText("Custom capacity follows contract terms"),
    ).toBeInTheDocument();
    expect(screen.getByText("Custom capacity active")).toBeInTheDocument();
    expect(screen.queryByText("21 over limit")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/beyond included allowance/i),
    ).not.toBeInTheDocument();
  });

  it("renders zero-credit self-serve capacity as exhausted", () => {
    render(
      <UsageCard
        usage={{
          ...usageSummary,
          plan: "free",
          analyses_used: 0,
          analyses_limit: 0,
          included_analyses_limit: 0,
          purchased_credits_balance: 0,
          usage_pct: 0,
          overage_analyses: 0,
        }}
      />,
    );

    expect(screen.getByText("0 / No limit set")).toBeInTheDocument();
    expect(screen.getByText("0 used")).toBeInTheDocument();
    expect(
      screen.getByText("No Report Credits are available this period"),
    ).toBeInTheDocument();
    expect(screen.getByText("No Report Credits available")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Buy Report Credits before launching a first-pass FTO analysis.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Custom capacity active"),
    ).not.toBeInTheDocument();
  });
});

describe("UpgradePlansCard", () => {
  it("offers only upgrades above the current tier and invokes checkout", () => {
    const onUpgrade = vi.fn();
    render(
      <UpgradePlansCard
        currentPlan="free"
        isCheckoutPending={false}
        upgradeTarget={null}
        onUpgrade={onUpgrade}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Upgrade to Starter/i }),
    );
    expect(onUpgrade).toHaveBeenCalledWith("starter");
    expect(
      screen.getByRole("button", { name: /Upgrade to Pro/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Review the Enterprise deployment boundary",
      }),
    ).toHaveAttribute("href", "/help#contact");
  });

  it("does not render lower paid tiers for pro customers", () => {
    render(
      <UpgradePlansCard
        currentPlan="pro"
        isCheckoutPending={false}
        upgradeTarget={null}
        onUpgrade={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /Upgrade to Starter/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Upgrade to Pro/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Review the Enterprise deployment boundary",
      }),
    ).toBeInTheDocument();
  });
});

describe("CreditPacksCard", () => {
  it("renders pay-as-you-go packs, volume deals, and invokes checkout", () => {
    const onBuyCredits = vi.fn();
    render(
      <CreditPacksCard
        availableReportCreditsBalance={6}
        purchasedCreditsBalance={6}
        includedAnalysesLimit={50}
        isCheckoutPending={false}
        creditPackTarget={null}
        onBuyCredits={onBuyCredits}
      />,
    );

    expect(
      screen.getByText("Prepaid Report Credit capacity"),
    ).toBeInTheDocument();
    expect(
      screen
        .getByRole("region", { name: "Prepaid Report Credit capacity" })
        .querySelector(".praviar-credit-ledger-field"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("billing-credit-ledger-field")).toHaveClass(
      "praviar-credit-ledger-field",
    );
    expect(screen.getByTestId("billing-credit-ledger-field-scrim")).toHaveClass(
      "bg-[var(--bg-surface)]/54",
    );
    expect(
      screen.getByText(
        "Add one-time report capacity without changing the subscription tier. Included Report Credits are always consumed first.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("1 Report Credit").length).toBeGreaterThan(0);
    expect(
      screen.getByText("1 first-pass FTO report request"),
    ).toBeInTheDocument();
    expect(screen.getByText("1 compound")).toBeInTheDocument();
    expect(screen.queryByTestId("credit-pack-rate-ladder")).toBeNull();
    expect(screen.queryByTestId("credit-header-quick-buy")).toBeNull();
    expect(screen.queryByTestId("credit-pack-decision-guide")).toBeNull();
    expect(
      screen.getByText(
        "Confirm current runway first; compare packs only when the planned demand needs more capacity.",
      ),
    ).toBeInTheDocument();
    const checkoutTerms = screen.getByRole("region", {
      name: "Before checkout terms",
    });
    expect(checkoutTerms).toHaveAttribute(
      "data-testid",
      "credit-pack-checkout-terms",
    );
    const termsDisclosure = checkoutTerms.querySelector("details");
    expect(termsDisclosure).not.toHaveAttribute("open");
    expect(
      within(checkoutTerms).getByText("Purchase terms and legal boundary"),
    ).toBeInTheDocument();
    fireEvent.click(
      within(checkoutTerms).getByText("Purchase terms and legal boundary"),
    );
    expect(termsDisclosure).toHaveAttribute("open");
    expect(
      within(checkoutTerms).getByText("Purchase type"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("One-time Report Credit Pack"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("Consumption order"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("50 included first"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("Stripe checkout"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("Hosted checkout · no card storage"),
    ).toBeInTheDocument();
    expect(within(checkoutTerms).getByText("Org scope")).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("Receipt + ledger"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("Legal boundary"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText("First-pass request"),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText(
        /non-refundable except where required by law or a signed order form/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(checkoutTerms).getByText(
        "Report Credits start source-linked first-pass workflows for counsel review, not legal conclusions.",
      ),
    ).toBeInTheDocument();
    const estimator = screen.getByRole("region", {
      name: "Match Report Credits to demand",
    });
    expect(
      checkoutTerms.compareDocumentPosition(estimator) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      within(estimator).getByText("Report Credit estimator"),
    ).toBeInTheDocument();
    expect(
      within(estimator).getByRole("button", { name: "5 reports" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(estimator).getByText("Recommendation for 5 reports"),
    ).toBeInTheDocument();
    expect(
      within(estimator).getByText("No purchase needed"),
    ).toBeInTheDocument();
    expect(within(estimator).getByText("Capacity covered")).toBeInTheDocument();
    const decisionFrame = within(estimator).getByTestId(
      "credit-estimator-covered-frame",
    );
    expect(decisionFrame).toHaveTextContent("Shortfall");
    expect(decisionFrame).toHaveTextContent("0");
    expect(decisionFrame).toHaveTextContent("After launch");
    expect(decisionFrame).toHaveTextContent("1");
    expect(decisionFrame).toHaveTextContent("Spend today");
    expect(decisionFrame).toHaveTextContent("$0");
    expect(estimator).toHaveTextContent(
      "Current capacity is 6 Report Credits, including 6 Report Credits purchased.",
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
    ).toHaveClass("min-h-11");
    expect(
      within(estimator).getByRole("link", {
        name: "Start analysis using existing capacity",
      }),
    ).toHaveAttribute("href", "/analyses/new");
    expect(
      within(estimator).queryByRole("button", {
        name: /Buy buffer/i,
      }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("$249 / report").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Recommended").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Best rate").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("region", { name: "Report Credit Pack options" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", {
        name: /Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("credit-pack-facts-portfolio_5"),
    ).toHaveTextContent("$229 / report");
    expect(screen.getAllByText("Single Report Credit").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Portfolio Pack").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Diligence Pack").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Scale Pack").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Recommended").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Recommended").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Best rate").length).toBeGreaterThan(0);
    expect(screen.getByText("$1,145")).toBeInTheDocument();
    expect(screen.getByText("$5,970")).toBeInTheDocument();
    expect(screen.getAllByText("Save 8%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Save 15%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Save 20%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$229 / report").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$212 / report").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$199 / report").length).toBeGreaterThan(0);
    expect(screen.getByText("Save 8% vs singles")).toBeInTheDocument();
    expect(screen.getByText("Save 20% vs singles")).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        "1 Report Credit = 1 first-pass FTO report request for 1 compound",
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /Buy Portfolio Pack, 5 Report Credits for \$1,145, Pilot team fit, Recommended, \$100 saved/i,
      }),
    );
    expect(onBuyCredits).toHaveBeenCalledWith("portfolio_5");
    fireEvent.click(
      within(estimator).getByRole("button", { name: "15 reports" }),
    );
    expect(
      within(estimator).getByText("Recommendation for 15 reports"),
    ).toBeInTheDocument();
    expect(within(estimator).getByText("Diligence Pack")).toBeInTheDocument();
    const purchaseDecisionFrame = within(estimator).getByTestId(
      "credit-estimator-decision-frame",
    );
    expect(purchaseDecisionFrame).toHaveTextContent("9 Report Credits");
    expect(purchaseDecisionFrame).toHaveTextContent("Lowest qualifying pack");
    expect(purchaseDecisionFrame).toHaveTextContent("6 Report Credits");
    expect(purchaseDecisionFrame).toHaveTextContent("$3,175");
    expect(estimator).toHaveTextContent("$560 saved vs singles");
    fireEvent.click(
      within(estimator).getByRole("button", {
        name: /Buy recommended Diligence Pack, 15 Report Credits for \$3,175/i,
      }),
    );
    expect(onBuyCredits).toHaveBeenCalledWith("diligence_15");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Buy Scale Pack, 30 Report Credits for \$5,970, Best unit price, Best rate, \$1,500 saved/i,
      }),
    );
    expect(onBuyCredits).toHaveBeenCalledWith("scale_30");
  });

  it("locks the estimator and keeps checkout state visible while opening Stripe", () => {
    const onBuyCredits = vi.fn();
    render(
      <CreditPacksCard
        availableReportCreditsBalance={6}
        purchasedCreditsBalance={6}
        includedAnalysesLimit={50}
        isCheckoutPending
        creditPackTarget="single_analysis"
        onBuyCredits={onBuyCredits}
      />,
    );

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
    expect(
      within(estimator).getByRole("button", {
        name: "Start analysis using existing capacity",
      }),
    ).toBeDisabled();
    expect(
      within(estimator).queryByRole("button", {
        name: /Buy buffer/i,
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      within(estimator).getByRole("button", { name: "15 reports" }),
    );
    expect(
      within(estimator).getByText("Recommendation for 5 reports"),
    ).toBeInTheDocument();
    expect(onBuyCredits).not.toHaveBeenCalled();
  });

  it("uses the provided launch return href for covered-capacity actions", () => {
    const onBuyCredits = vi.fn();
    const launchReturnHref =
      "/analyses/new?resume=credit_checkout&launch_draft_id=ld_card_123";

    render(
      <CreditPacksCard
        availableReportCreditsBalance={6}
        purchasedCreditsBalance={6}
        includedAnalysesLimit={50}
        initialReportNeed={5}
        isCheckoutPending={false}
        creditPackTarget={null}
        launchReturnHref={launchReturnHref}
        onBuyCredits={onBuyCredits}
      />,
    );

    expect(
      within(
        screen.getByRole("region", {
          name: "Match Report Credits to demand",
        }),
      ).getByRole("link", {
        name: "Start analysis using existing capacity",
      }),
    ).toHaveAttribute("href", launchReturnHref);
  });

  it("resets the estimator when a new URL-backed report need arrives", () => {
    const props = {
      availableReportCreditsBalance: 0,
      purchasedCreditsBalance: 0,
      includedAnalysesLimit: 50,
      isCheckoutPending: false,
      creditPackTarget: null,
      onBuyCredits: vi.fn(),
    };
    const { rerender } = render(
      <CreditPacksCard {...props} initialReportNeed={5} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "15 reports" }));
    expect(
      screen.getByText("Recommendation for 15 reports"),
    ).toBeInTheDocument();

    rerender(<CreditPacksCard {...props} initialReportNeed={1} />);

    expect(screen.getByText("Recommendation for 1 report")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 report" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("hides covered-capacity launch links when the role cannot create analyses", () => {
    render(
      <CreditPacksCard
        availableReportCreditsBalance={6}
        canStartAnalysis={false}
        purchasedCreditsBalance={6}
        includedAnalysesLimit={50}
        initialReportNeed={5}
        isCheckoutPending={false}
        creditPackTarget={null}
        onBuyCredits={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("link", { name: "Start analysis" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", {
        name: "Start analysis using existing capacity",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "This role can review capacity but cannot start a new analysis.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps low prepaid credit balance visible in the estimator", () => {
    render(
      <CreditPacksCard
        availableReportCreditsBalance={2}
        purchasedCreditsBalance={2}
        includedAnalysesLimit={50}
        isCheckoutPending={false}
        creditPackTarget={null}
        onBuyCredits={vi.fn()}
      />,
    );

    const estimator = screen.getByRole("region", {
      name: "Match Report Credits to demand",
    });
    expect(estimator).toHaveTextContent(
      "Current capacity is 2 Report Credits, including 2 Report Credits purchased.",
    );
  });
});

describe("InvoiceHistoryCard", () => {
  it("renders loading and empty states", () => {
    const { rerender } = render(
      <InvoiceHistoryCard isLoading invoiceData={undefined} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading invoice history",
    );
    expect(screen.queryByText("No invoices yet")).not.toBeInTheDocument();

    rerender(
      <InvoiceHistoryCard
        isLoading={false}
        invoiceData={{ invoices: [], has_more: false }}
      />,
    );
    expect(screen.getByText("No invoices yet")).toBeInTheDocument();
    expect(
      screen.getByText("Invoices will appear here after your first payment"),
    ).toBeInTheDocument();
  });

  it("renders invoice load failures without pretending the account has no invoices", () => {
    const onRetry = vi.fn();
    render(
      <InvoiceHistoryCard
        isLoading={false}
        error={new Error("stripe 503")}
        invoiceData={undefined}
        onRetry={onRetry}
      />,
    );

    expect(
      screen.getByText("Invoice history temporarily unavailable"),
    ).toBeInTheDocument();
    expect(screen.queryByText("No invoices yet")).not.toBeInTheDocument();
    expect(screen.queryByText(/stripe 503/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry invoice load" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("warns when stale invoice history is shown after a refresh failure", () => {
    const invoiceData: InvoiceListResponse = {
      has_more: false,
      invoices: [
        {
          id: "in_stale_123456",
          number: "SG-2026-0001",
          status: "paid",
          amount_due_cents: 49_900,
          amount_paid_cents: 49_900,
          currency: "usd",
          created_at: "2026-04-01T00:00:00.000Z",
          hosted_invoice_url: null,
          pdf_url: null,
        },
      ],
    };

    render(
      <InvoiceHistoryCard
        isLoading={false}
        error={new Error("refresh failed")}
        invoiceData={invoiceData}
      />,
    );

    expect(screen.getByText("SG-2026-0001")).toBeInTheDocument();
    expect(screen.getByText(/Invoice refresh failed/i)).toBeInTheDocument();
    expect(screen.queryByText(/^refresh failed$/i)).not.toBeInTheDocument();
  });

  it("hides cached invoice rows and document links after an auth boundary error", () => {
    const invoiceData: InvoiceListResponse = {
      has_more: true,
      invoices: [
        {
          id: "in_private_123456",
          number: "SG-2026-0042",
          status: "paid",
          amount_due_cents: 49_900,
          amount_paid_cents: 49_900,
          currency: "usd",
          created_at: "2026-04-01T00:00:00.000Z",
          hosted_invoice_url: "https://invoice.stripe.com/i/in_private",
          pdf_url: "https://pay.stripe.com/invoice/in_private/pdf",
        },
      ],
    };

    render(
      <InvoiceHistoryCard
        isLoading={false}
        error={new APIError(403, "Forbidden")}
        invoiceData={invoiceData}
      />,
    );

    expect(
      screen.getByText("Invoice history access restricted"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Cached invoice rows and document links are hidden/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("SG-2026-0042")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Additional invoice history/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "View invoice SG-2026-0042" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", {
        name: "Download invoice SG-2026-0042 PDF",
      }),
    ).not.toBeInTheDocument();
  });

  it("discloses when only the latest invoice page is shown", () => {
    const invoiceData: InvoiceListResponse = {
      has_more: true,
      invoices: [
        {
          id: "in_more_123456",
          number: "SG-2026-0002",
          status: "paid",
          amount_due_cents: 49_900,
          amount_paid_cents: 49_900,
          currency: "usd",
          created_at: "2026-04-01T00:00:00.000Z",
          hosted_invoice_url: null,
          pdf_url: null,
        },
      ],
    };

    render(<InvoiceHistoryCard isLoading={false} invoiceData={invoiceData} />);

    expect(
      screen.getByText(/Additional invoice history is available/i),
    ).toBeInTheDocument();
  });

  it("suppresses unsafe and non-Stripe invoice document links", () => {
    const invoiceData: InvoiceListResponse = {
      has_more: false,
      invoices: [
        {
          id: "in_bad_123456789",
          number: "SG-2026-0003",
          status: "paid",
          amount_due_cents: 49_900,
          amount_paid_cents: 49_900,
          currency: "usd",
          created_at: "2026-04-01T00:00:00.000Z",
          hosted_invoice_url: "https://evil.example/invoice",
          pdf_url: "data:text/html,hi",
        },
      ],
    };

    render(<InvoiceHistoryCard isLoading={false} invoiceData={invoiceData} />);

    expect(screen.getByText("SG-2026-0003")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "View invoice SG-2026-0003" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", {
        name: "Download invoice SG-2026-0003 PDF",
      }),
    ).not.toBeInTheDocument();
  });

  it("renders invoice rows with fallback invoice ID, status, amount, and links", () => {
    const invoiceData: InvoiceListResponse = {
      has_more: false,
      invoices: [
        {
          id: "in_123456789abcdef",
          number: null,
          status: "open",
          amount_due_cents: 49_900,
          amount_paid_cents: 0,
          currency: "usd",
          created_at: "2026-04-01T00:00:00.000Z",
          hosted_invoice_url: "https://invoice.stripe.com/i/in_123456789abcdef",
          pdf_url: "https://pay.stripe.com/invoice/in_123456789abcdef/pdf",
        },
      ],
    };

    render(<InvoiceHistoryCard isLoading={false} invoiceData={invoiceData} />);

    const row = screen.getByText("in_123456789").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row!).getByText("open")).toBeInTheDocument();
    expect(within(row!).getByText("$499.00")).toBeInTheDocument();
    const viewInvoice = within(row!).getByRole("link", {
      name: "View invoice in_123456789",
    });
    const downloadPdf = within(row!).getByRole("link", {
      name: "Download invoice in_123456789 PDF",
    });

    expect(viewInvoice).toHaveAttribute(
      "href",
      "https://invoice.stripe.com/i/in_123456789abcdef",
    );
    expect(viewInvoice).toHaveClass("min-h-11", "px-3");
    expect(downloadPdf).toHaveAttribute(
      "href",
      "https://pay.stripe.com/invoice/in_123456789abcdef/pdf",
    );
    expect(downloadPdf).toHaveClass("min-h-11", "px-3");
  });
});

describe("BillingHeader", () => {
  it("only renders the manage-subscription action when a subscription exists", () => {
    const onManageSubscription = vi.fn();
    const { container, rerender } = render(
      <BillingHeader
        hasSubscription
        isManagingSubscription={false}
        onManageSubscription={onManageSubscription}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Credits & Billing" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Buy Report Credits, manage plan capacity, and review usage",
      ),
    ).toBeInTheDocument();
    expect(
      container.querySelector('[data-praviar-mark-frame="light"]'),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Manage Subscription/i }),
    );
    expect(onManageSubscription).toHaveBeenCalledTimes(1);

    rerender(
      <BillingHeader
        hasSubscription={false}
        isManagingSubscription={false}
        onManageSubscription={onManageSubscription}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /Manage Subscription/i }),
    ).not.toBeInTheDocument();
  });
});
