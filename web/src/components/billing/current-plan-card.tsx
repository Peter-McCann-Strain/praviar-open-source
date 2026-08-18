"use client";

import {
  CalendarClock,
  CheckCircle,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BillingStatus, PlanTier } from "@/hooks/use-billing";
import {
  PLAN_DETAILS,
  formatDate,
  formatSubscriptionStatus,
} from "@/components/billing/helpers";

interface CurrentPlanCardProps {
  billingStatus?: BillingStatus;
  currentPlan: PlanTier;
}

export function CurrentPlanCard({
  billingStatus,
  currentPlan,
}: CurrentPlanCardProps) {
  const planInfo = PLAN_DETAILS[currentPlan];
  const status = billingStatus?.subscription_status ?? null;
  const hasBillingPeriod = Boolean(
    billingStatus?.current_period_start || billingStatus?.current_period_end,
  );
  const statusVariant =
    status === "active"
      ? "success"
      : status === "past_due"
        ? "destructive"
        : "secondary";

  return (
    <Card className="praviar-account-control-card overflow-hidden">
      <CardHeader className="praviar-account-control-header border-b border-[var(--border-subtle)]">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ShieldCheck
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <CardTitle className="text-sm">Subscription status</CardTitle>
            </div>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              Plan entitlement and renewal posture for this organization.
            </p>
          </div>
          <Badge variant={planInfo.badgeVariant} className="shrink-0">
            {planInfo.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-5 sm:p-6">
        <div className="grid gap-5 md:grid-cols-[minmax(0,0.82fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Current plan
            </p>
            <p className="mt-2 type-heading-xl text-[var(--text-primary)]">
              {planInfo.price}
            </p>
            <p className="mt-1 type-body-md text-[var(--text-secondary)]">
              {planInfo.description}
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Badge variant={statusVariant}>
                {formatSubscriptionStatus(status)}
              </Badge>
              {billingStatus?.cancel_at_period_end ? (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/25 bg-warning/10 px-2.5 py-0.5 text-xs font-semibold text-warning">
                  <TriangleAlert className="h-3 w-3" aria-hidden="true" />
                  Cancels at period end
                </span>
              ) : null}
            </div>
          </div>

          <div className="praviar-account-metric-panel min-w-0 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <CalendarClock
                className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Renewal period
                </p>
                <p className="mt-1 text-sm tabular-nums text-[var(--text-secondary)]">
                  {billingStatus?.current_period_start &&
                  billingStatus.current_period_end
                    ? `${formatDate(billingStatus.current_period_start)} - ${formatDate(
                        billingStatus.current_period_end,
                      )}`
                    : billingStatus?.current_period_start
                      ? `Started ${formatDate(billingStatus.current_period_start)}`
                      : billingStatus?.current_period_end
                        ? `Ends ${formatDate(billingStatus.current_period_end)}`
                        : "No renewal scheduled"}
                </p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                  {!hasBillingPeriod
                    ? "A renewal period appears after a subscription is active."
                    : billingStatus?.cancel_at_period_end
                      ? "Access remains through the current period unless the subscription is reactivated."
                      : "Subscription changes are managed through the hosted billing portal."}
                </p>
              </div>
            </div>
          </div>
        </div>

        <ul className="grid gap-2 sm:grid-cols-2">
          {planInfo.features.map((feature) => (
            <li
              key={feature}
              className="flex min-w-0 items-center gap-2 text-sm text-[var(--text-secondary)]"
            >
              <CheckCircle
                className="h-3.5 w-3.5 flex-shrink-0 text-success"
                aria-hidden="true"
              />
              <span className="min-w-0 break-words">{feature}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
