"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  CheckCircle,
  Crown,
  FileSearch,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PlanTier } from "@/hooks/use-billing";
import { PLAN_DETAILS } from "@/components/billing/helpers";
import { WORKSPACE_SUPPORT_BOUNDARY_HREF } from "@/lib/support-boundary";

interface UpgradePlansCardProps {
  actionsDisabled?: boolean;
  currentPlan: PlanTier;
  isCheckoutPending: boolean;
  upgradeTarget: PlanTier | null;
  onUpgrade: (plan: PlanTier) => void;
}

export function UpgradePlansCard({
  actionsDisabled = false,
  currentPlan,
  isCheckoutPending,
  upgradeTarget,
  onUpgrade,
}: UpgradePlansCardProps) {
  const tiers: PlanTier[] = ["free", "starter", "pro", "enterprise"];
  const eligiblePlans = (["starter", "pro", "enterprise"] as PlanTier[]).filter(
    (plan) => tiers.indexOf(plan) > tiers.indexOf(currentPlan),
  );

  return (
    <Card className="praviar-account-control-card overflow-hidden">
      <CardHeader className="praviar-account-control-header border-b border-[var(--border-subtle)]">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
            <Crown className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <CardTitle className="text-sm">Plan change controls</CardTitle>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              Checkout opens in Stripe-hosted billing; no payment details are
              entered or stored in Praviar.
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-5 sm:p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {eligiblePlans.map((planId) => {
            const plan = PLAN_DETAILS[planId];
            const isEnterprise = planId === "enterprise";

            return (
              <div
                key={planId}
                className={`flex min-w-0 flex-col rounded-lg p-5 ${
                  planId === "pro"
                    ? "praviar-plan-option-card-featured"
                    : "praviar-plan-option-card"
                }`}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 break-words type-heading-md text-[var(--text-primary)]">
                      {plan.label}
                    </span>
                    {planId === "pro" ? (
                      <Badge variant="default">Popular</Badge>
                    ) : null}
                  </div>
                  <p className="mt-1 type-heading-md text-brand-primary">
                    {plan.price}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                    {plan.description}
                  </p>
                </div>
                <ul className="mt-4 grow space-y-1.5">
                  {plan.features.slice(0, 3).map((feature) => (
                    <li
                      key={feature}
                      className="flex min-w-0 items-start gap-1.5 text-xs leading-5 text-[var(--text-secondary)]"
                    >
                      <CheckCircle
                        className="mt-1 h-3 w-3 flex-shrink-0 text-success"
                        aria-hidden="true"
                      />
                      <span className="min-w-0 break-words">{feature}</span>
                    </li>
                  ))}
                </ul>
                {isEnterprise ? (
                  <Button
                    asChild
                    variant="outline"
                    className="mt-5 min-h-11 w-full gap-2"
                  >
                    <Link
                      href={WORKSPACE_SUPPORT_BOUNDARY_HREF}
                      aria-label="Review the Enterprise deployment boundary"
                    >
                      <FileSearch className="h-4 w-4" aria-hidden="true" />
                      Review deployment path
                    </Link>
                  </Button>
                ) : (
                  <Button
                    className="mt-5 min-h-11 w-full gap-2"
                    onClick={() => onUpgrade(planId)}
                    loading={upgradeTarget === planId}
                    disabled={actionsDisabled || isCheckoutPending}
                  >
                    <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                    Upgrade to {plan.label}
                  </Button>
                )}
                {isEnterprise ? (
                  <p className="mt-2 flex items-start gap-1.5 text-xs leading-4 text-[var(--text-tertiary)]">
                    <Zap
                      className="mt-0.5 h-3 w-3 shrink-0"
                      aria-hidden="true"
                    />
                    Enterprise terms, SSO, and SLAs are not offered by this
                    research preview.
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
