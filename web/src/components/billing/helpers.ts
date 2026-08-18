import type { CreditPackId, PlanTier } from "@/hooks/use-billing";

export const REPORT_CREDIT_CONTRACT_COPY =
  "1 Report Credit = 1 first-pass FTO report request for 1 compound";

export const PLAN_INCLUDED_CREDITS: Record<PlanTier, number | null> = {
  free: 2,
  starter: 25,
  pro: 100,
  enterprise: null,
};

export const PLAN_DETAILS: Record<
  PlanTier,
  {
    label: string;
    description: string;
    price: string;
    features: string[];
    badgeVariant: "default" | "secondary" | "success" | "warning";
  }
> = {
  free: {
    label: "Free",
    description: "Try Praviar on a compound you already know.",
    price: "$0/mo",
    features: [
      `${PLAN_INCLUDED_CREDITS.free} included Report Credits per month`,
      "US screening",
      "Evidence trail inside each report",
    ],
    badgeVariant: "secondary",
  },
  starter: {
    label: "Starter",
    description: "For founders and small teams running repeat screens.",
    price: "$499/mo",
    features: [
      `${PLAN_INCLUDED_CREDITS.starter} included Report Credits per month`,
      "Configured patent, chemistry and literature sources",
      "Source-health and reviewer trail",
      "PDF export",
    ],
    badgeVariant: "default",
  },
  pro: {
    label: "Pro",
    description: "For IP and diligence teams working across markets.",
    price: "$1,499/mo",
    features: [
      `${PLAN_INCLUDED_CREDITS.pro} included Report Credits per month`,
      "Up to 9 target jurisdictions; source gaps shown",
      "API access subject to workspace review",
      "PDF export and reviewer workflow",
    ],
    badgeVariant: "success",
  },
  enterprise: {
    label: "Enterprise",
    description:
      "For organizations that need SSO, dedicated infrastructure, and contracted service terms.",
    price: "Custom",
    features: [
      "Contracted Report Credit pool",
      "Contracted overflow capacity through order form",
      "Dedicated infrastructure subject to signed scope",
      "SSO & SAML subject to signed scope",
      "Service levels defined in signed order form",
      "Dedicated support",
    ],
    badgeVariant: "warning",
  },
};

export const CREDIT_PACK_DETAILS: Record<
  CreditPackId,
  {
    label: string;
    shortLabel: string;
    description: string;
    fitLabel: string;
    credits: number;
    priceCents: number;
    savingsLabel: string | null;
    featured?: boolean;
    bestValue?: boolean;
  }
> = {
  single_analysis: {
    label: "Single Report Credit",
    shortLabel: "Single Report Credit",
    description:
      "For a one-off FTO question without moving into a subscription tier.",
    fitLabel: "One report request",
    credits: 1,
    priceCents: 24_900,
    savingsLabel: null,
  },
  portfolio_5: {
    label: "Portfolio Pack",
    shortLabel: "Portfolio Pack",
    description:
      "Best fit for founder diligence, board prep, or a focused patent sweep.",
    fitLabel: "Small portfolio",
    credits: 5,
    priceCents: 114_500,
    savingsLabel: "Save 8%",
    featured: true,
  },
  diligence_15: {
    label: "Diligence Pack",
    shortLabel: "Diligence Pack",
    description:
      "Volume pricing for repeat screening across a pipeline or transaction set.",
    fitLabel: "Diligence process",
    credits: 15,
    priceCents: 317_500,
    savingsLabel: "Save 15%",
  },
  scale_30: {
    label: "Scale Pack",
    shortLabel: "Scale Pack",
    description:
      "Best self-serve rate for IP teams screening a larger portfolio before counsel review.",
    fitLabel: "Portfolio scale",
    credits: 30,
    priceCents: 597_000,
    savingsLabel: "Save 20%",
    bestValue: true,
  },
};

export function formatReportCreditCount(value: number): string {
  return `${value.toLocaleString()} ${
    value === 1 ? "Report Credit" : "Report Credits"
  }`;
}

export function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function formatCurrency(cents: number, currency = "usd"): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency.toUpperCase(),
    }).format(cents / 100);
  } catch {
    return formatCents(cents);
  }
}

export function formatCreditPackPrice(cents: number, currency = "usd"): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency.toUpperCase(),
      maximumFractionDigits: 0,
    }).format(cents / 100);
  } catch {
    return `$${Math.round(cents / 100).toLocaleString("en-US")}`;
  }
}

export function isCreditPackId(
  value: string | null | undefined,
): value is CreditPackId {
  return Boolean(
    value && Object.prototype.hasOwnProperty.call(CREDIT_PACK_DETAILS, value),
  );
}

export function formatDate(iso: string | null): string {
  if (!iso) {
    return "N/A";
  }

  return new Date(iso).toLocaleDateString("en-US", {
    timeZone: "UTC",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatSubscriptionStatus(status: string | null): string {
  if (!status) return "No subscription";
  return status
    .replace(/[_-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function getRemainingAnalyses(
  used: number,
  limit: number,
): number | null {
  if (limit <= 0) return null;
  return Math.max(0, limit - used);
}

const ALLOWED_STRIPE_REDIRECT_HOSTS = new Set([
  "checkout.stripe.com",
  "billing.stripe.com",
]);
const ALLOWED_STRIPE_BILLING_DOCUMENT_HOSTS = new Set([
  "billing.stripe.com",
  "invoice.stripe.com",
  "pay.stripe.com",
]);

export function isAllowedStripeRedirectUrl(value: string) {
  const origin =
    typeof window !== "undefined" ? window.location.origin : undefined;
  try {
    const parsed = new URL(value, origin);
    // Same-origin redirects are only allowed for explicit absolute URLs on our
    // origin or root-relative paths (e.g. the demo "/billing?demo_checkout=..."
    // URL). A bare string like "not a url" parses as a relative path against
    // the origin and must NOT be treated as a trusted redirect target.
    if (origin && parsed.origin === origin) {
      return (
        value.startsWith("http://") ||
        value.startsWith("https://") ||
        value.startsWith("/")
      );
    }
    return (
      parsed.protocol === "https:" &&
      ALLOWED_STRIPE_REDIRECT_HOSTS.has(parsed.hostname)
    );
  } catch {
    return false;
  }
}

export function safeBillingDocumentHref(
  value: string | null | undefined,
): string | undefined {
  if (!value) return undefined;

  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" &&
      ALLOWED_STRIPE_BILLING_DOCUMENT_HOSTS.has(parsed.hostname)
      ? value
      : undefined;
  } catch {
    return undefined;
  }
}
