"use client";

import { AlertTriangle, BarChart3, CheckCircle, Gauge } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UsageMeter } from "@/components/billing/usage-meter";
import {
  formatDate,
  formatReportCreditCount,
} from "@/components/billing/helpers";
import type { UsageSummary } from "@/hooks/use-billing";

interface UsageCardProps {
  usage?: UsageSummary;
}

interface UsageCapacityModel {
  capacityDescription: string | null;
  capacityTextClass: string;
  capacityTitle: string;
  capacityToneClass: string;
  hasConfiguredLimit: boolean;
  hasOverage: boolean;
  isCapacityExhausted: boolean;
  isNearLimit: boolean;
  isZeroCreditCapacity: boolean;
  remainingAnalyses: number | null;
  remainingDetail: string;
  usageLedgerDetail: string;
}

interface UsageCapacityFacts {
  hasConfiguredLimit: boolean;
  hasOverage: boolean;
  hasPurchasedCreditLedger: boolean;
  includedCreditsLeft: number;
  includedCreditsUsed: number;
  isCapacityExhausted: boolean;
  isEnterpriseCustomCapacity: boolean;
  isNearLimit: boolean;
  isZeroCreditCapacity: boolean;
  purchasedCreditsLeft: number;
  purchasedCreditsUsed: number;
  remainingAnalyses: number | null;
}

type CapacityStatusFacts = Pick<
  UsageCapacityFacts,
  | "hasConfiguredLimit"
  | "hasOverage"
  | "isCapacityExhausted"
  | "isEnterpriseCustomCapacity"
  | "isNearLimit"
  | "isZeroCreditCapacity"
  | "remainingAnalyses"
>;

type CreditLedgerFacts = Pick<
  UsageCapacityFacts,
  | "hasPurchasedCreditLedger"
  | "includedCreditsLeft"
  | "includedCreditsUsed"
  | "purchasedCreditsLeft"
  | "purchasedCreditsUsed"
>;

function getRemainingAnalyses(
  usage: UsageSummary | undefined,
  hasConfiguredLimit: boolean,
  isEnterpriseCustomCapacity: boolean,
) {
  if (!usage) return null;
  if (hasConfiguredLimit) {
    return Math.max(0, usage.analyses_limit - usage.analyses_used);
  }
  return isEnterpriseCustomCapacity ? null : 0;
}

function deriveCapacityStatusFacts(
  usage: UsageSummary | undefined,
): CapacityStatusFacts {
  const hasConfiguredLimit = Boolean(usage && usage.analyses_limit > 0);
  const isEnterpriseCustomCapacity = Boolean(
    usage && usage.plan === "enterprise" && !hasConfiguredLimit,
  );
  const isZeroCreditCapacity = Boolean(
    usage && usage.plan !== "enterprise" && !hasConfiguredLimit,
  );
  const remainingAnalyses = getRemainingAnalyses(
    usage,
    hasConfiguredLimit,
    isEnterpriseCustomCapacity,
  );
  const hasOverage = Boolean(
    usage && hasConfiguredLimit && usage.overage_analyses > 0,
  );
  const isCapacityExhausted = Boolean(
    usage &&
    !hasOverage &&
    (isZeroCreditCapacity || (hasConfiguredLimit && remainingAnalyses === 0)),
  );
  const isNearLimit = Boolean(
    usage &&
    hasConfiguredLimit &&
    !isCapacityExhausted &&
    usage.usage_pct >= 80 &&
    usage.overage_analyses <= 0,
  );
  return {
    hasConfiguredLimit,
    hasOverage,
    isCapacityExhausted,
    isEnterpriseCustomCapacity,
    isNearLimit,
    isZeroCreditCapacity,
    remainingAnalyses,
  };
}

function deriveCreditLedgerFacts(
  usage: UsageSummary | undefined,
): CreditLedgerFacts {
  const includedCreditLimit = usage
    ? (usage.included_analyses_limit ?? usage.analyses_limit)
    : 0;
  const purchasedCreditsUsed = usage?.purchased_credits_used ?? 0;
  const planAnalysesUsed = usage
    ? Math.max(usage.analyses_used - purchasedCreditsUsed, 0)
    : 0;
  const includedCreditsUsed = usage
    ? Math.min(planAnalysesUsed, includedCreditLimit)
    : 0;
  const includedCreditsLeft = usage
    ? Math.max(includedCreditLimit - includedCreditsUsed, 0)
    : 0;
  const purchasedCreditsLeft = usage?.purchased_credits_balance ?? 0;
  const hasPurchasedCreditLedger = Boolean(
    usage && (purchasedCreditsUsed > 0 || purchasedCreditsLeft > 0),
  );
  return {
    hasPurchasedCreditLedger,
    includedCreditsLeft,
    includedCreditsUsed,
    purchasedCreditsLeft,
    purchasedCreditsUsed,
  };
}

function deriveUsageCapacityFacts(
  usage: UsageSummary | undefined,
): UsageCapacityFacts {
  return {
    ...deriveCapacityStatusFacts(usage),
    ...deriveCreditLedgerFacts(usage),
  };
}

function getCapacityToneClass(facts: UsageCapacityFacts) {
  if (facts.hasOverage || facts.isZeroCreditCapacity) {
    return "border-error/20 bg-error/[0.07]";
  }
  if (facts.isCapacityExhausted || facts.isNearLimit) {
    return "border-warning/20 bg-warning/10";
  }
  return "border-success/20 bg-success/10";
}

function getCapacityTextClass(facts: UsageCapacityFacts) {
  if (facts.hasOverage || facts.isZeroCreditCapacity) return "text-error";
  if (facts.isCapacityExhausted || facts.isNearLimit) return "text-warning";
  return "text-success";
}

function getCapacityTitle(
  usage: UsageSummary | undefined,
  facts: UsageCapacityFacts,
) {
  if (!usage) return "";
  if (facts.hasOverage) {
    const unit = usage.overage_analyses === 1 ? "analysis" : "analyses";
    return `${usage.overage_analyses.toLocaleString()} ${unit} beyond available Report Credits`;
  }
  if (facts.isZeroCreditCapacity) return "No Report Credits available";
  if (facts.isCapacityExhausted) return "Allowance fully used";
  if (facts.isNearLimit) return "Approaching plan limit";
  return facts.hasConfiguredLimit
    ? "Usage within allowance"
    : "Custom capacity active";
}

function getCapacityDescription(
  usage: UsageSummary | undefined,
  facts: UsageCapacityFacts,
) {
  if (!usage) return null;
  if (facts.hasOverage) {
    return "Buy Report Credits or adjust plan capacity before launching additional large FTO batches.";
  }
  if (facts.isZeroCreditCapacity) {
    return "Buy Report Credits before launching a first-pass FTO analysis.";
  }
  if (facts.isCapacityExhausted) {
    return "Review Report Credit Packs or plan capacity before approving more analyses this period.";
  }
  if (facts.isNearLimit) {
    return "Consider Report Credits or plan capacity before approving more analyses this period.";
  }
  return facts.hasConfiguredLimit
    ? "Included allowance is available; purchased Report Credits remain separate for extra work."
    : "Usage is tracked for visibility; contracted capacity is managed outside self-serve limits.";
}

function getUsageLedgerDetail(
  usage: UsageSummary | undefined,
  facts: UsageCapacityFacts,
) {
  if (!usage) return "Usage data not loaded";
  if (facts.isEnterpriseCustomCapacity) {
    return "Custom capacity follows contract terms";
  }
  if (facts.isZeroCreditCapacity) {
    return "No Report Credits are available this period";
  }
  if (facts.hasOverage) {
    return `${facts.includedCreditsUsed.toLocaleString()} included used, ${usage.overage_analyses.toLocaleString()} over available credits`;
  }
  if (facts.hasPurchasedCreditLedger) {
    return `${facts.includedCreditsUsed.toLocaleString()} included used, ${formatPurchasedCreditUsage(facts.purchasedCreditsUsed)}`;
  }
  return "Counted against current included allowance";
}

function getRemainingDetail(
  usage: UsageSummary | undefined,
  facts: UsageCapacityFacts,
) {
  if (!usage) return "Usage data not loaded";
  if (facts.isEnterpriseCustomCapacity) return "Contracted capacity";
  if (facts.hasPurchasedCreditLedger) {
    return formatPurchasedCreditBalance(facts.purchasedCreditsLeft);
  }
  return facts.hasConfiguredLimit
    ? `${facts.includedCreditsLeft.toLocaleString()} included left`
    : "No self-serve capacity";
}

function deriveUsageCapacity(
  usage: UsageSummary | undefined,
): UsageCapacityModel {
  const facts = deriveUsageCapacityFacts(usage);
  return {
    capacityDescription: getCapacityDescription(usage, facts),
    capacityTextClass: getCapacityTextClass(facts),
    capacityTitle: getCapacityTitle(usage, facts),
    capacityToneClass: getCapacityToneClass(facts),
    hasConfiguredLimit: facts.hasConfiguredLimit,
    hasOverage: facts.hasOverage,
    isCapacityExhausted: facts.isCapacityExhausted,
    isNearLimit: facts.isNearLimit,
    isZeroCreditCapacity: facts.isZeroCreditCapacity,
    remainingAnalyses: facts.remainingAnalyses,
    remainingDetail: getRemainingDetail(usage, facts),
    usageLedgerDetail: getUsageLedgerDetail(usage, facts),
  };
}

function CapacityNotice({ capacity }: { capacity: UsageCapacityModel }) {
  const showWarning =
    capacity.hasOverage ||
    capacity.isZeroCreditCapacity ||
    capacity.isCapacityExhausted ||
    capacity.isNearLimit;
  const warningClass =
    capacity.hasOverage || capacity.isZeroCreditCapacity
      ? "text-error"
      : "text-warning";
  return (
    <div
      className={`rounded-lg border px-4 py-3 ${capacity.capacityToneClass}`}
    >
      <div className="flex items-start gap-2">
        {showWarning ? (
          <AlertTriangle
            className={`mt-0.5 h-4 w-4 shrink-0 ${warningClass}`}
            aria-hidden="true"
          />
        ) : (
          <CheckCircle
            className="mt-0.5 h-4 w-4 shrink-0 text-success"
            aria-hidden="true"
          />
        )}
        <div className="min-w-0">
          <p className={`text-sm font-medium ${capacity.capacityTextClass}`}>
            {capacity.capacityTitle}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {capacity.capacityDescription}
          </p>
        </div>
      </div>
    </div>
  );
}

export function UsageCard({ usage }: UsageCardProps) {
  const capacity = deriveUsageCapacity(usage);

  return (
    <Card className="praviar-account-control-card overflow-hidden">
      <CardHeader className="praviar-account-control-header border-b border-[var(--border-subtle)]">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Gauge
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <CardTitle className="text-sm">Analysis capacity</CardTitle>
            </div>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              Billing-period usage, remaining allowance, and purchased Report
              Credit capacity.
            </p>
          </div>
          <BarChart3
            className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]"
            aria-hidden="true"
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-5 sm:p-6">
        <UsageMeter
          limitConfigured={capacity.hasConfiguredLimit}
          used={usage?.analyses_used ?? 0}
          limit={usage?.analyses_limit ?? 0}
          pct={usage?.usage_pct ?? 0}
        />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="praviar-account-metric-panel rounded-lg p-3">
            <p className="type-label-sm text-[var(--text-tertiary)]">
              Usage ledger
            </p>
            <p className="type-heading-md mt-0.5 tabular-nums text-[var(--text-primary)]">
              {usage
                ? `${usage.analyses_used.toLocaleString()} used`
                : "0 used"}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              {capacity.usageLedgerDetail}
            </p>
          </div>
          <div className="praviar-account-metric-panel rounded-lg p-3">
            <p className="type-label-sm text-[var(--text-tertiary)]">
              Remaining
            </p>
            <p className="mt-0.5 type-heading-md tabular-nums text-[var(--text-primary)]">
              {capacity.remainingAnalyses === null
                ? "Not set"
                : formatReportCreditCount(capacity.remainingAnalyses)}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              {capacity.remainingDetail}
            </p>
          </div>
          <div className="praviar-account-metric-panel rounded-lg p-3 sm:col-span-1">
            <p className="type-label-sm text-[var(--text-tertiary)]">Period</p>
            <p className="mt-0.5 type-body-md text-[var(--text-primary)]">
              {usage?.period_start && usage?.period_end
                ? `${formatDate(usage.period_start)} - ${formatDate(usage.period_end)}`
                : "Current month"}
            </p>
          </div>
        </div>

        {usage ? <CapacityNotice capacity={capacity} /> : null}
      </CardContent>
    </Card>
  );
}

function formatPurchasedCreditUsage(value: number) {
  return `${value.toLocaleString()} purchased ${
    value === 1 ? "credit" : "credits"
  } used`;
}

function formatPurchasedCreditBalance(value: number) {
  return `${value.toLocaleString()} purchased ${
    value === 1 ? "credit" : "credits"
  } left`;
}
