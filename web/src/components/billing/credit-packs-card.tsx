"use client";

import Link from "next/link";
import { useId, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BadgePercent,
  LockKeyhole,
  PackagePlus,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  CREDIT_PACK_DETAILS,
  REPORT_CREDIT_CONTRACT_COPY,
  formatCreditPackPrice,
  formatReportCreditCount,
} from "@/components/billing/helpers";
import type { CreditPackId } from "@/hooks/use-billing";
import { cn } from "@/lib/utils";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";

interface CreditPacksCardProps {
  actionsDisabled?: boolean;
  availableReportCreditsBalance: number;
  canStartAnalysis?: boolean;
  purchasedCreditsBalance: number;
  includedAnalysesLimit: number;
  initialReportNeed?: number;
  isCheckoutPending: boolean;
  creditPackTarget: CreditPackId | null;
  spotlightCreditPackId?: CreditPackId | null;
  launchReturnHref?: string;
  onBuyCredits: (creditPackId: CreditPackId) => void;
}

type CreditPackComparison = {
  effectiveRateCents: number;
  pack: (typeof CREDIT_PACK_DETAILS)[CreditPackId];
  packId: CreditPackId;
  savingsCents: number;
};

const CREDIT_PACK_PURCHASE_GUIDANCE: Record<
  CreditPackId,
  {
    badge: string;
    buyerFit: string;
    decisionCue: string;
    workflow: string;
  }
> = {
  single_analysis: {
    badge: "One-off analysis",
    buyerFit: "Answer one urgent FTO question without committing budget.",
    decisionCue: "Smallest commitment",
    workflow: "Founder question or counsel follow-up",
  },
  portfolio_5: {
    badge: "Pilot team fit",
    buyerFit: "Cover a focused set of compounds for board or investor review.",
    decisionCue: "Save 8%",
    workflow: "Board prep or focused patent sweep",
  },
  diligence_15: {
    badge: "Diligence sprint",
    buyerFit: "Keep repeat screening moving across a transaction or pipeline.",
    decisionCue: "Save 15%",
    workflow: "Deal room or pipeline screen",
  },
  scale_30: {
    badge: "Best unit price",
    buyerFit: "Screen a larger portfolio before outside-counsel review.",
    decisionCue: "Save 20%",
    workflow: "Quarterly portfolio review",
  },
};

export function CreditPacksCard({
  actionsDisabled = false,
  availableReportCreditsBalance,
  canStartAnalysis = true,
  purchasedCreditsBalance,
  includedAnalysesLimit,
  initialReportNeed,
  isCheckoutPending,
  creditPackTarget,
  spotlightCreditPackId = null,
  launchReturnHref = "/analyses/new",
  onBuyCredits,
}: CreditPacksCardProps) {
  const titleId = useId();
  const estimatorId = useId();
  const packOptionsId = useId();
  const purchaseAccessReasonId = useId();
  const packs = Object.entries(CREDIT_PACK_DETAILS) as Array<
    [CreditPackId, (typeof CREDIT_PACK_DETAILS)[CreditPackId]]
  >;
  const packComparisons = packs.map(([packId, pack]) => {
    const singleCreditPriceCents =
      CREDIT_PACK_DETAILS.single_analysis.priceCents;
    const listPriceCents = singleCreditPriceCents * pack.credits;
    const savingsCents = Math.max(listPriceCents - pack.priceCents, 0);
    const effectiveRateCents = Math.round(pack.priceCents / pack.credits);

    return {
      effectiveRateCents,
      pack,
      packId,
      savingsCents,
    };
  });
  const spotlightPack = spotlightCreditPackId
    ? CREDIT_PACK_DETAILS[spotlightCreditPackId]
    : null;
  const availableReportCredits = Math.max(availableReportCreditsBalance, 0);
  const purchasedCredits = Math.max(purchasedCreditsBalance, 0);
  const checkoutPendingLabel = creditPackTarget
    ? CREDIT_PACK_DETAILS[creditPackTarget].shortLabel
    : null;

  return (
    <Card
      id="credit-packs"
      className="scroll-mt-24 overflow-hidden"
      role="region"
      aria-labelledby={titleId}
    >
      <CardHeader
        className="praviar-credit-ledger-field relative isolate overflow-hidden border-b border-[var(--border-subtle)] p-4 sm:p-6"
        data-testid="billing-credit-ledger-field"
      >
        <div
          className="pointer-events-none absolute inset-0 z-0 bg-[var(--bg-surface)]/54 backdrop-blur-[1px]"
          aria-hidden="true"
          data-testid="billing-credit-ledger-field-scrim"
        />
        <div className="relative z-10">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-accent/30 bg-brand-accent/10 text-brand-accent shadow-[var(--shadow-xs)]">
              <PackagePlus className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2
                id={titleId}
                className="type-heading-md text-xl text-[var(--text-primary)] sm:text-2xl"
              >
                Prepaid Report Credit capacity
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                Add one-time report capacity without changing the subscription
                tier. Included Report Credits are always consumed first.
              </p>
              <div
                className="mt-3 flex w-fit max-w-full flex-wrap items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]"
                aria-label={REPORT_CREDIT_CONTRACT_COPY}
              >
                <span className="rounded-md border border-brand-primary/16 bg-[var(--bg-surface)]/78 px-2.5 py-1.5 text-[var(--text-primary)] shadow-[var(--shadow-xs)] backdrop-blur">
                  1 Report Credit
                </span>
                <ArrowRight
                  className="h-3.5 w-3.5 text-brand-primary"
                  aria-hidden="true"
                />
                <span>1 first-pass FTO report request</span>
                <ArrowRight
                  className="h-3.5 w-3.5 text-brand-primary"
                  aria-hidden="true"
                />
                <span>1 compound</span>
              </div>
              {actionsDisabled ? (
                <p
                  id={purchaseAccessReasonId}
                  className="mt-3 max-w-3xl rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs font-semibold leading-5 text-[var(--text-primary)]"
                  role="note"
                >
                  Report Credit checkout requires a workspace administrator.
                  Capacity, pricing, and effective-rate comparisons remain
                  available for review.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4 sm:p-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">
              Plan Report Credit capacity
            </h3>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              Confirm current runway first; compare packs only when the planned
              demand needs more capacity.
            </p>
          </div>
          <div className="inline-flex w-fit items-center gap-2 text-xs leading-5 text-[var(--text-tertiary)]">
            <LockKeyhole
              className="h-3.5 w-3.5 shrink-0 text-brand-primary"
              aria-hidden="true"
            />
            <span>
              Stripe-hosted checkout shows final tax and receipt details.
            </span>
          </div>
        </div>

        {spotlightPack ? (
          <div
            role="status"
            className="rounded-lg border border-brand-primary/25 bg-brand-primary/8 px-4 py-3 text-sm text-[var(--text-secondary)]"
          >
            <span className="font-semibold text-[var(--text-primary)]">
              Selected from pricing:
            </span>{" "}
            {spotlightPack.label} is highlighted below.
          </div>
        ) : null}

        <CreditCheckoutTermsPanel
          includedAnalysesLimit={includedAnalysesLimit}
        />

        <CreditNeedEstimator
          key={`credit-need:${initialReportNeed ?? "default"}`}
          availableReportCreditsBalance={availableReportCredits}
          estimatorId={estimatorId}
          initialReportNeed={initialReportNeed}
          packComparisons={packComparisons}
          purchasedCreditsBalance={purchasedCredits}
          isCheckoutPending={isCheckoutPending}
          launchReturnHref={launchReturnHref}
          canStartAnalysis={canStartAnalysis}
          actionsDisabled={actionsDisabled}
          purchaseAccessReasonId={purchaseAccessReasonId}
          targetPackId={creditPackTarget}
          onBuyCredits={onBuyCredits}
        />

        <ResponsiveDisclosure
          className="group"
          summary={
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
              <span>
                <span className="block text-sm font-semibold text-[var(--text-primary)]">
                  Compare all 4 Report Credit Packs
                </span>
                <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                  From 1 to 30 reports · see price, savings, and checkout
                </span>
              </span>
              <ArrowRight
                className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-90"
                aria-hidden="true"
              />
            </summary>
          }
        >
          <section
            id="credit-pack-options"
            aria-labelledby={packOptionsId}
            className="mt-3 sm:mt-0 sm:block"
          >
            <h3 id={packOptionsId} className="sr-only">
              Report Credit Pack options
            </h3>
            <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
              <div className="hidden grid-cols-[minmax(13rem,1.25fr)_0.62fr_0.72fr_0.72fr_minmax(9rem,0.9fr)] gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] xl:grid">
                <span>Pack</span>
                <span>Report Credits</span>
                <span>Price</span>
                <span>Effective</span>
                <span className="text-right">Checkout</span>
              </div>
              <div className="divide-y divide-[var(--border-subtle)]">
                {packComparisons.map((comparison) => (
                  <CreditPackRow
                    key={comparison.packId}
                    comparison={comparison}
                    actionsDisabled={actionsDisabled}
                    purchaseAccessReasonId={purchaseAccessReasonId}
                    isCheckoutPending={isCheckoutPending}
                    isSpotlight={spotlightCreditPackId === comparison.packId}
                    onBuyCredits={onBuyCredits}
                    targetPackId={creditPackTarget}
                  />
                ))}
              </div>
            </div>
          </section>
        </ResponsiveDisclosure>

        {checkoutPendingLabel ? (
          <p className="sr-only" role="status">
            Opening Stripe checkout for {checkoutPendingLabel}.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CreditCheckoutTermsPanel({
  includedAnalysesLimit,
}: {
  includedAnalysesLimit: number;
}) {
  const termItems = [
    {
      detail:
        "Credit packs do not auto-renew or change your subscription tier.",
      label: "Purchase type",
      value: "One-time Report Credit Pack",
    },
    {
      detail: "Plan allowance is consumed before purchased Report Credits.",
      label: "Consumption order",
      value: `${includedAnalysesLimit.toLocaleString()} included first`,
    },
    {
      detail:
        "Tax, final amount, payment method, and receipt details stay in Stripe; Praviar does not store card details.",
      label: "Stripe checkout",
      value: "Hosted checkout · no card storage",
    },
    {
      detail:
        "Credits attach to this organization and preserve launch-capacity evidence.",
      label: "Org scope",
      value: "Receipt + ledger",
    },
    {
      detail:
        "Report Credits start source-linked first-pass workflows for counsel review, not legal conclusions.",
      label: "Legal boundary",
      value: "First-pass request",
    },
  ];

  return (
    <section
      aria-label="Before checkout terms"
      data-testid="credit-pack-checkout-terms"
    >
      <details className="group overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/44 shadow-[var(--shadow-xs)]">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-primary/70 [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              Purchase terms and legal boundary
            </span>
            <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
              One-time pack · included credits first · Stripe hosted ·
              organization scoped
            </span>
          </span>
          <ArrowRight
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
        </summary>
        <div className="border-t border-[var(--border-subtle)]">
          <div className="grid min-w-0 divide-y divide-[var(--border-subtle)] sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-5">
            {termItems.map(({ detail, label, value }) => (
              <div
                key={label}
                className="min-w-0 bg-[var(--bg-surface)]/70 px-3 py-3"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  {label}
                </p>
                <p className="mt-0.5 break-words text-sm font-semibold leading-5 text-[var(--text-primary)]">
                  {value}
                </p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                  {detail}
                </p>
              </div>
            ))}
          </div>
          <p className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-4 py-3 text-xs leading-5 text-[var(--text-secondary)]">
            Credits are generally non-refundable except where required by law or
            a signed order form; expiry, tax, and final receipt details are
            reviewed before payment.
          </p>
        </div>
      </details>
    </section>
  );
}

function CreditNeedEstimator({
  actionsDisabled,
  availableReportCreditsBalance,
  estimatorId,
  initialReportNeed,
  isCheckoutPending,
  launchReturnHref,
  canStartAnalysis,
  onBuyCredits,
  packComparisons,
  purchaseAccessReasonId,
  purchasedCreditsBalance,
  targetPackId,
}: {
  actionsDisabled: boolean;
  availableReportCreditsBalance: number;
  estimatorId: string;
  initialReportNeed?: number;
  isCheckoutPending: boolean;
  launchReturnHref: string;
  canStartAnalysis: boolean;
  onBuyCredits: (creditPackId: CreditPackId) => void;
  packComparisons: CreditPackComparison[];
  purchaseAccessReasonId: string;
  purchasedCreditsBalance: number;
  targetPackId: CreditPackId | null;
}) {
  const [reportNeed, setReportNeed] = useState(initialReportNeed ?? 5);
  const availableReportCredits = Math.max(availableReportCreditsBalance, 0);
  const additionalCreditsNeeded = Math.max(
    reportNeed - availableReportCredits,
    0,
  );
  const recommendedComparison = getRecommendedComparisonForNeed(
    packComparisons,
    Math.max(additionalCreditsNeeded, 1),
  );
  const { effectiveRateCents, pack, packId, savingsCents } =
    recommendedComparison;
  const projectedRunway = availableReportCredits + pack.credits;
  const projectedBufferAfterRun = Math.max(projectedRunway - reportNeed, 0);
  const guidance = CREDIT_PACK_PURCHASE_GUIDANCE[packId];
  const checkoutLabel = `Buy ${pack.shortLabel}`;
  const checkoutPendingPackLabel = targetPackId
    ? CREDIT_PACK_DETAILS[targetPackId].label
    : "selected pack";
  const recommendationRationale = getCreditPackRecommendationRationale({
    additionalCreditsNeeded,
    packCredits: pack.credits,
  });

  return (
    <section
      aria-labelledby={estimatorId}
      aria-busy={isCheckoutPending}
      className="grid gap-3 rounded-lg border border-brand-primary/18 bg-brand-primary/8 p-3 shadow-[var(--shadow-xs)] sm:p-4 md:grid-cols-[minmax(0,1fr)_minmax(16rem,0.58fr)] md:items-start"
      data-testid="credit-need-estimator"
    >
      <div className="min-w-0">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
              Report Credit estimator
            </p>
            <h3
              id={estimatorId}
              className="mt-1 text-base font-semibold text-[var(--text-primary)]"
            >
              Match Report Credits to demand
            </h3>
            <p className="mt-1 hidden max-w-2xl text-xs leading-5 text-[var(--text-secondary)] sm:block">
              Pick the number of first-pass FTO report requests you expect to
              launch. Praviar subtracts current launch capacity before
              recommending a pack, so buyers see commitment, runway, effective
              rate, and savings before checkout.
            </p>
          </div>
          <Badge
            variant={
              additionalCreditsNeeded === 0
                ? "success"
                : pack.featured
                  ? "default"
                  : pack.bestValue
                    ? "success"
                    : "secondary"
            }
          >
            {additionalCreditsNeeded === 0
              ? "Capacity covered"
              : guidance.badge}
          </Badge>
        </div>

        <div
          role="group"
          aria-label="Expected first-pass FTO report requests"
          className="mt-3 grid grid-cols-2 gap-2 sm:inline-grid sm:grid-cols-4"
        >
          {[1, 5, 15, 30].map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={reportNeed === option}
              disabled={isCheckoutPending}
              onClick={() => setReportNeed(option)}
              className={cn(
                "min-h-11 rounded-md border px-3 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] disabled:pointer-events-none disabled:opacity-55",
                reportNeed === option
                  ? "border-brand-primary/40 bg-brand-primary-dim text-[var(--brand-paper)] shadow-[var(--shadow-sm)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-surface)]/82 text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
              )}
            >
              {option} {option === 1 ? "report" : "reports"}
            </button>
          ))}
        </div>
      </div>

      <div
        role="status"
        aria-live="polite"
        className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/82 p-3 shadow-[var(--shadow-xs)] sm:p-4"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Recommendation for {reportNeed}{" "}
          {reportNeed === 1 ? "report" : "reports"}
        </p>
        {isCheckoutPending ? (
          <p className="mt-2 rounded-md border border-brand-primary/20 bg-brand-primary/10 px-3 py-2 text-xs font-semibold text-brand-primary">
            Opening checkout for {checkoutPendingPackLabel}.
          </p>
        ) : null}
        <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {additionalCreditsNeeded === 0 ? "No purchase needed" : pack.label}
        </p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          {additionalCreditsNeeded === 0
            ? "Current launch capacity covers this run. Continue without checkout."
            : guidance.buyerFit}
        </p>
        {additionalCreditsNeeded === 0 ? (
          <dl
            className="mt-3 grid grid-cols-3 gap-2"
            data-testid="credit-estimator-covered-frame"
          >
            <CoveredCapacityMetric label="Shortfall" value="0" />
            <CoveredCapacityMetric
              label="After launch"
              value={Math.max(
                availableReportCredits - reportNeed,
                0,
              ).toLocaleString()}
            />
            <CoveredCapacityMetric label="Spend today" value="$0" />
          </dl>
        ) : (
          <CreditEstimatorDecisionFrame
            additionalCreditsNeeded={additionalCreditsNeeded}
            packPriceCents={pack.priceCents}
            projectedBufferAfterRun={projectedBufferAfterRun}
            recommendationRationale={recommendationRationale}
          />
        )}
        <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
          {additionalCreditsNeeded === 0 ? (
            <>
              Current capacity is{" "}
              {formatReportCreditCount(availableReportCredits)}, including{" "}
              {formatReportCreditCount(purchasedCreditsBalance)} purchased. No
              additional Report Credits are required.
            </>
          ) : (
            <>
              {formatReportCreditCount(pack.credits)} at{" "}
              <span className="font-semibold tabular-nums text-[var(--text-primary)]">
                {formatCreditPackPrice(effectiveRateCents)} / report
              </span>
              {savingsCents > 0
                ? ` · ${formatCreditPackPrice(savingsCents)} saved vs singles`
                : " · single-credit price anchor"}
              . Current capacity is{" "}
              {formatReportCreditCount(availableReportCredits)}, including{" "}
              {formatReportCreditCount(purchasedCreditsBalance)} purchased.
            </>
          )}
        </p>
        {additionalCreditsNeeded === 0 ? (
          <div className="mt-3 grid min-w-0 gap-2 sm:mt-4">
            {!canStartAnalysis ? (
              <p
                className="rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs font-semibold leading-5 text-[var(--text-primary)]"
                role="note"
              >
                This role can review capacity but cannot start a new analysis.
              </p>
            ) : isCheckoutPending ? (
              <Button
                className="h-auto min-h-11 min-w-0 max-w-full w-full gap-2 whitespace-normal py-2 text-center leading-5"
                disabled
              >
                <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                Start analysis using existing capacity
              </Button>
            ) : (
              <Button
                asChild
                className="h-auto min-h-11 min-w-0 max-w-full w-full gap-2 whitespace-normal py-2 text-center leading-5"
              >
                <Link href={launchReturnHref}>
                  <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Start analysis using existing capacity
                </Link>
              </Button>
            )}
          </div>
        ) : (
          <Button
            className="mt-3 h-auto min-h-11 min-w-0 max-w-full w-full gap-2 whitespace-normal py-2 text-center leading-5 sm:mt-4"
            variant={pack.featured || pack.bestValue ? "default" : "outline"}
            onClick={() => onBuyCredits(packId)}
            loading={targetPackId === packId}
            disabled={actionsDisabled || isCheckoutPending}
            aria-describedby={
              actionsDisabled ? purchaseAccessReasonId : undefined
            }
            aria-label={`Buy recommended ${pack.label}, ${formatAnalysisCreditLabel(
              pack.credits,
            )} for ${formatCreditPackPrice(pack.priceCents)}`}
          >
            <ArrowUpRight className="h-4 w-4 shrink-0" aria-hidden="true" />
            {checkoutLabel}
          </Button>
        )}
      </div>
    </section>
  );
}

function CoveredCapacityMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-success/20 bg-success/8 px-2 py-2">
      <dt className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}

function CreditPackRow({
  actionsDisabled,
  comparison,
  isCheckoutPending,
  isSpotlight,
  onBuyCredits,
  purchaseAccessReasonId,
  targetPackId,
}: {
  actionsDisabled: boolean;
  comparison: CreditPackComparison;
  isCheckoutPending: boolean;
  isSpotlight: boolean;
  onBuyCredits: (creditPackId: CreditPackId) => void;
  purchaseAccessReasonId: string;
  targetPackId: CreditPackId | null;
}) {
  const { effectiveRateCents, pack, packId, savingsCents } = comparison;
  const guidance = CREDIT_PACK_PURCHASE_GUIDANCE[packId];
  const hasSavings = savingsCents > 0;
  const rowGuidance = [
    guidance.badge,
    pack.featured ? "Recommended" : null,
    pack.bestValue ? "Best rate" : null,
    hasSavings ? `${formatCreditPackPrice(savingsCents)} saved` : null,
  ]
    .filter(Boolean)
    .join(", ");
  const rowLabel = `${pack.label}, ${formatAnalysisCreditLabel(
    pack.credits,
  )} for ${formatCreditPackPrice(pack.priceCents)}${
    rowGuidance ? `, ${rowGuidance}` : ""
  }`;

  return (
    <article
      id={`credit-pack-${packId}`}
      aria-label={rowLabel}
      className={cn(
        "grid min-w-0 grid-cols-2 gap-3 border-l-4 border-transparent bg-[var(--bg-surface)] p-3 transition-colors sm:p-4 xl:grid-cols-[minmax(13rem,1.25fr)_0.62fr_0.72fr_0.72fr_minmax(9rem,0.9fr)] xl:items-center",
        isSpotlight
          ? "border-brand-primary bg-brand-primary/10 ring-2 ring-inset ring-brand-primary/35"
          : pack.featured
            ? "border-brand-primary/70 bg-brand-primary/5"
            : pack.bestValue
              ? "border-success/70 bg-success/5"
              : hasSavings
                ? "border-brand-accent/40 hover:bg-[var(--surface-hover)]"
                : "hover:bg-[var(--surface-hover)]",
      )}
      data-credit-pack-row={packId}
      tabIndex={isSpotlight ? -1 : undefined}
    >
      <div className="col-span-2 min-w-0 xl:col-span-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h4 className="break-words text-sm font-semibold text-[var(--text-primary)]">
            {pack.label}
          </h4>
          {isSpotlight ? <Badge variant="default">Selected</Badge> : null}
          {pack.featured ? <Badge variant="default">Recommended</Badge> : null}
          {pack.bestValue ? <Badge variant="success">Best rate</Badge> : null}
          {pack.savingsLabel ? (
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-success">
              <BadgePercent className="h-3 w-3" aria-hidden="true" />
              {pack.savingsLabel}
            </span>
          ) : null}
        </div>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          {pack.fitLabel}
        </p>
        <p className="mt-1 text-xs font-semibold leading-5 text-brand-primary">
          {guidance.workflow}
        </p>
      </div>

      <PackColumn
        label="Report Credits"
        value={formatReportCreditCount(pack.credits)}
      />
      <PackColumn
        label="Price"
        value={formatCreditPackPrice(pack.priceCents)}
        detail="USD"
      />
      <PackColumn
        label="Effective"
        value={`${formatCreditPackPrice(effectiveRateCents)} / report`}
        detail={hasSavings ? `${guidance.decisionCue} vs singles` : "Anchor"}
        testId={`credit-pack-facts-${packId}`}
      />

      <div className="col-span-2 min-w-0 xl:col-span-1 xl:text-right">
        <Button
          className="min-h-11 w-full min-w-0 gap-2 whitespace-normal px-3 text-center leading-5 xl:w-auto xl:whitespace-nowrap"
          variant={pack.featured || pack.bestValue ? "default" : "outline"}
          onClick={() => onBuyCredits(packId)}
          loading={targetPackId === packId}
          disabled={actionsDisabled || isCheckoutPending}
          aria-describedby={
            actionsDisabled ? purchaseAccessReasonId : undefined
          }
          aria-label={`Buy ${rowLabel}`}
        >
          <ArrowUpRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          Buy {pack.shortLabel}
        </Button>
      </div>
    </article>
  );
}

function PackColumn({
  detail,
  label,
  testId,
  value,
}: {
  detail?: string;
  label: string;
  testId?: string;
  value: string;
}) {
  return (
    <div className="min-w-0" data-testid={testId}>
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] xl:hidden">
        {label}
      </p>
      <p className="break-words text-sm font-semibold leading-5 text-[var(--text-primary)]">
        {value}
      </p>
      {detail ? (
        <p className="mt-0.5 hidden text-xs leading-5 text-[var(--text-tertiary)] sm:block">
          {detail}
        </p>
      ) : null}
    </div>
  );
}

function CreditEstimatorDecisionFrame({
  additionalCreditsNeeded,
  packPriceCents,
  projectedBufferAfterRun,
  recommendationRationale,
}: {
  additionalCreditsNeeded: number;
  packPriceCents: number;
  projectedBufferAfterRun: number;
  recommendationRationale: string;
}) {
  const decisionItems = [
    {
      label: "Shortfall",
      value: formatReportCreditCount(additionalCreditsNeeded),
    },
    {
      label: "Why this pack",
      value: recommendationRationale,
    },
    {
      label: "Post-run buffer",
      value: formatReportCreditCount(projectedBufferAfterRun),
    },
    {
      label: "Spend today",
      value: formatCreditPackPrice(packPriceCents),
    },
  ];

  return (
    <div
      className="mt-3 grid gap-2 rounded-md border border-brand-primary/15 bg-brand-primary/5 p-2 sm:grid-cols-2"
      data-testid="credit-estimator-decision-frame"
    >
      {decisionItems.map(({ label, value }) => (
        <div
          key={label}
          className="min-w-0 rounded-sm bg-[var(--bg-surface)]/72 px-2.5 py-2"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            {label}
          </p>
          <p className="mt-0.5 break-words text-xs font-semibold leading-5 text-[var(--text-primary)]">
            {value}
          </p>
        </div>
      ))}
    </div>
  );
}

function formatAnalysisCreditLabel(value: number) {
  return formatReportCreditCount(value);
}

function getCreditPackRecommendationRationale({
  additionalCreditsNeeded,
  packCredits,
}: {
  additionalCreditsNeeded: number;
  packCredits: number;
}) {
  if (additionalCreditsNeeded === 0) {
    return "Optional buffer";
  }

  if (packCredits === additionalCreditsNeeded) {
    return "Exact-fit pack";
  }

  return "Lowest qualifying pack";
}

function getRecommendedComparisonForNeed(
  packComparisons: CreditPackComparison[],
  reportNeed: number,
) {
  const sortedBySize = [...packComparisons].sort(
    (left, right) => left.pack.credits - right.pack.credits,
  );
  return (
    sortedBySize.find(({ pack }) => pack.credits >= reportNeed) ??
    sortedBySize[sortedBySize.length - 1] ??
    packComparisons[0]
  );
}
